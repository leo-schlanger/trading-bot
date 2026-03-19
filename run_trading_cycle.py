"""
Trading Cycle - Executado a cada 4 horas via GitHub Actions.

Este script:
1. Carrega dados recentes
2. Detecta regime de mercado
3. Seleciona estratégia
4. Verifica sinais
5. Executa trades (se em modo live)
6. Envia notificações
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np

from src.ml.regime_detector import RegimeDetector, MarketRegime
from src.ml.strategy_selector import StrategySelector, StrategyType, STRATEGY_NAMES
from src.ml.features import FeatureGenerator
from src.optimization.risk_manager import RiskManager, RiskConfig
from src.optimization.param_optimizer import ParamOptimizer
from src.bot.safety_controls import SafetyControls, CircuitBreakerConfig
from src.indicators.technical import atr, sma
from src.notifications import TelegramNotifier, notify_error

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/trading_cycle.log')
    ]
)
logger = logging.getLogger(__name__)


class TradingCycle:
    """Executa um ciclo de análise e trading."""

    def __init__(self, mode: str = 'paper'):
        self.mode = mode
        self.state_file = Path('state/trading_state.json')
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Componentes
        self.regime_detector = RegimeDetector()
        self.strategy_selector = StrategySelector()
        self.feature_generator = FeatureGenerator()
        self.param_optimizer = ParamOptimizer()

        # Carregar estado anterior
        self.state = self._load_state()

        # Risk manager
        capital = self.state.get('capital', 500.0)
        risk_config = RiskConfig(initial_capital=capital)
        self.risk_manager = RiskManager(risk_config)

        # Safety controls
        cb_config = CircuitBreakerConfig(initial_capital=capital)
        self.safety_controls = SafetyControls(cb_config)

        # Restaurar estado do risk manager
        if 'risk_state' in self.state:
            self._restore_risk_state()

    def _load_state(self) -> Dict[str, Any]:
        """Carrega estado da última execução."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Erro ao carregar estado: {e}")

        return {
            'capital': 500.0,
            'position': None,
            'last_regime': None,
            'consecutive_losses': 0,
            'total_trades': 0,
            'total_pnl': 0.0
        }

    def _save_state(self):
        """Salva estado para próxima execução."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
            logger.info("Estado salvo com sucesso")
        except Exception as e:
            logger.error(f"Erro ao salvar estado: {e}")

    def _restore_risk_state(self):
        """Restaura estado do risk manager."""
        rs = self.state.get('risk_state', {})
        self.risk_manager.state.current_capital = rs.get('capital', 500.0)
        self.risk_manager.state.peak_capital = rs.get('peak', 500.0)
        self.risk_manager.state.consecutive_losses = rs.get('consecutive_losses', 0)

    def load_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Carrega dados recentes do símbolo."""
        data_file = Path(f'data/raw/{symbol}_4h.csv')

        if not data_file.exists():
            logger.error(f"Arquivo de dados não encontrado: {data_file}")
            return None

        try:
            df = pd.read_csv(data_file, index_col=0, parse_dates=True)
            df = df.sort_index()

            # Verificar se dados são recentes (últimas 8 horas)
            last_candle = df.index[-1]
            hours_old = (datetime.now() - last_candle.to_pydatetime().replace(tzinfo=None)).total_seconds() / 3600

            if hours_old > 8:
                logger.warning(f"Dados podem estar desatualizados ({hours_old:.1f}h)")

            logger.info(f"Carregados {len(df)} candles de {symbol}, último: {last_candle}")
            return df

        except Exception as e:
            logger.error(f"Erro ao carregar dados: {e}")
            return None

    def analyze(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Analisa mercado e gera recomendação."""
        result = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'regime': None,
            'strategy': None,
            'signal': 0,
            'confidence': 0,
            'action': 'HOLD',
            'details': {}
        }

        # Verificar dados suficientes
        if len(df) < 200:
            result['action'] = 'SKIP'
            result['details']['reason'] = 'Dados insuficientes'
            return result

        # Calcular ATR
        df = df.copy()
        df['atr'] = atr(df['high'], df['low'], df['close'], 14)
        df['atr_ma'] = sma(df['atr'], 20)

        current_atr = df['atr'].iloc[-1]
        avg_atr = df['atr_ma'].iloc[-1]

        # 1. Detectar regime
        regime, regime_scores = self.regime_detector.detect(df)
        result['regime'] = regime.value
        result['details']['regime_scores'] = regime_scores

        logger.info(f"Regime detectado: {regime.value}")

        # 2. Safety checks
        safety_result = self.safety_controls.check_all(regime, current_atr, avg_atr)

        if not safety_result['can_trade']:
            result['action'] = 'BLOCKED'
            result['details']['safety'] = safety_result
            blockers = safety_result.get('blockers', [])
            logger.warning(f"Trading bloqueado: {blockers}")

            # Notificar circuit breaker via Telegram
            try:
                notifier = TelegramNotifier()
                if notifier.is_configured() and blockers:
                    notifier.send_circuit_breaker(
                        reason=blockers[0] if blockers else "Safety check failed",
                        details={
                            "symbol": symbol,
                            "regime": regime.value,
                            "all_blockers": ", ".join(blockers)
                        }
                    )
            except Exception as e:
                logger.error(f"Erro ao notificar circuit breaker: {e}")

            return result

        # 3. Selecionar estratégia
        strategy_type, confidence, prob_dict = self.strategy_selector.select_strategy(df, regime)
        result['strategy'] = STRATEGY_NAMES[strategy_type]
        result['confidence'] = confidence
        result['details']['strategy_probs'] = prob_dict

        logger.info(f"Estratégia selecionada: {STRATEGY_NAMES[strategy_type]} (confiança: {confidence:.2f})")

        # 4. Gerar features e verificar sinal
        features = self.feature_generator.get_strategy_features(df)
        latest = features.iloc[-1] if len(features) > 0 else None

        if latest is not None:
            # Análise simplificada de sinal baseada em features
            signal = self._generate_signal(df, regime, strategy_type)
            result['signal'] = signal

            if signal > 0:
                result['action'] = 'BUY'
            elif signal < 0:
                result['action'] = 'SELL'
            else:
                result['action'] = 'HOLD'

        # 5. Calcular position size se houver sinal
        if result['signal'] != 0:
            close = df['close'].iloc[-1]
            stop_distance = current_atr * 2.0

            if result['signal'] > 0:
                stop_loss = close - stop_distance
            else:
                stop_loss = close + stop_distance

            sizing = self.risk_manager.get_position_size(regime, close, stop_loss)
            sizing['position_value'] *= safety_result.get('position_multiplier', 1.0)

            result['details']['sizing'] = sizing
            result['details']['price'] = close
            result['details']['stop_loss'] = stop_loss

        return result

    def _generate_signal(self, df: pd.DataFrame, regime: MarketRegime, strategy: StrategyType) -> int:
        """Gera sinal simplificado baseado em indicadores."""
        close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]

        # Features básicas
        rsi = df['close'].diff().apply(lambda x: max(x, 0)).rolling(14).mean() / \
              df['close'].diff().abs().rolling(14).mean() * 100
        rsi_val = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

        ma_50 = df['close'].rolling(50).mean().iloc[-1]
        ma_200 = df['close'].rolling(200).mean().iloc[-1]

        # Supertrend direction (simplificado)
        atr_val = df['atr'].iloc[-1] if 'atr' in df.columns else 0
        upper = (df['high'] + df['low']) / 2 + (3 * atr_val)
        lower = (df['high'] + df['low']) / 2 - (3 * atr_val)
        trend_up = close > lower.iloc[-1]

        signal = 0

        # Lógica por regime
        if regime == MarketRegime.BULL:
            # Em bull, procurar continuação de tendência
            if close > ma_50 > ma_200 and rsi_val < 70 and trend_up:
                signal = 1
            elif rsi_val > 80:
                signal = -1  # Overbought

        elif regime == MarketRegime.BEAR:
            # Em bear, mais conservador
            if close < ma_50 < ma_200 and rsi_val > 30 and not trend_up:
                signal = -1
            elif rsi_val < 20:
                signal = 1  # Oversold bounce

        elif regime == MarketRegime.SIDEWAYS:
            # Mean reversion
            if rsi_val < 30:
                signal = 1
            elif rsi_val > 70:
                signal = -1

        elif regime == MarketRegime.CORRECTION:
            # Muito conservador - só oversold extremo
            if rsi_val < 25:
                signal = 1

        return signal

    def execute(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Executa a ação recomendada."""
        result = {
            'executed': False,
            'action': analysis['action'],
            'mode': self.mode,
            'details': {}
        }

        if analysis['action'] in ['HOLD', 'SKIP', 'BLOCKED']:
            logger.info(f"Nenhuma ação: {analysis['action']}")
            return result

        if self.mode == 'backtest':
            logger.info("Modo backtest - simulando execução")
            result['executed'] = True
            result['details']['simulated'] = True

        elif self.mode == 'paper':
            logger.info("Modo paper trading - registrando trade simulado")
            result['executed'] = True
            result['details']['paper_trade'] = True

            # Simular trade no estado
            self._simulate_paper_trade(analysis)

        elif self.mode == 'live':
            logger.info("Modo LIVE - executando trade real")
            # TODO: Integrar com exchange API
            # result = self._execute_live_trade(analysis)
            logger.warning("Execução live não implementada ainda")

        return result

    def _simulate_paper_trade(self, analysis: Dict[str, Any]):
        """Simula trade em paper trading."""
        if 'sizing' not in analysis['details']:
            return

        trade = {
            'timestamp': analysis['timestamp'],
            'symbol': analysis['symbol'],
            'action': analysis['action'],
            'price': analysis['details'].get('price', 0),
            'size': analysis['details']['sizing'].get('position_size', 0),
            'value': analysis['details']['sizing'].get('position_value', 0)
        }

        # Salvar no estado
        if 'paper_trades' not in self.state:
            self.state['paper_trades'] = []
        self.state['paper_trades'].append(trade)
        self.state['total_trades'] = len(self.state['paper_trades'])

    def send_notification(self, analysis: Dict[str, Any], execution: Dict[str, Any]):
        """Envia notificação via Telegram."""
        try:
            notifier = TelegramNotifier()

            if not notifier.is_configured():
                logger.info("Telegram não configurado, pulando notificação")
                return

            # Extrair dados
            details = analysis.get('details', {})
            sizing = details.get('sizing', {})

            notifier.send_trade_signal(
                symbol=analysis['symbol'],
                action=analysis['action'],
                regime=analysis['regime'] or 'unknown',
                strategy=analysis['strategy'] or 'unknown',
                confidence=analysis['confidence'],
                price=details.get('price'),
                stop_loss=details.get('stop_loss'),
                position_size=sizing.get('position_value'),
                executed=execution.get('executed', False),
                mode=self.mode
            )

            logger.info("Notificação enviada")

        except Exception as e:
            logger.error(f"Erro ao enviar notificação: {e}")

    def run(self, symbols: list = None):
        """Executa ciclo completo de trading."""
        symbols = symbols or ['BTC', 'ETH']

        logger.info("=" * 50)
        logger.info(f"Iniciando ciclo de trading - {datetime.now()}")
        logger.info(f"Modo: {self.mode}")
        logger.info(f"Símbolos: {symbols}")
        logger.info("=" * 50)

        results = []

        for symbol in symbols:
            logger.info(f"\n--- Analisando {symbol} ---")

            # Carregar dados
            df = self.load_data(symbol)
            if df is None:
                continue

            # Analisar
            analysis = self.analyze(df, symbol)

            # Executar
            execution = self.execute(analysis)

            # Notificar
            if analysis['action'] not in ['HOLD', 'SKIP']:
                self.send_notification(analysis, execution)

            results.append({
                'symbol': symbol,
                'analysis': analysis,
                'execution': execution
            })

        # Salvar estado
        self.state['last_run'] = datetime.now().isoformat()
        self.state['risk_state'] = {
            'capital': self.risk_manager.state.current_capital,
            'peak': self.risk_manager.state.peak_capital,
            'consecutive_losses': self.risk_manager.state.consecutive_losses
        }
        self._save_state()

        # Resumo
        logger.info("\n" + "=" * 50)
        logger.info("RESUMO DO CICLO")
        logger.info("=" * 50)
        for r in results:
            logger.info(f"{r['symbol']}: {r['analysis']['action']} ({r['analysis']['regime']})")

        return results


def main():
    parser = argparse.ArgumentParser(description='Trading Cycle')
    parser.add_argument('--mode', choices=['backtest', 'paper', 'live'],
                        default=os.getenv('TRADING_MODE', 'paper'))
    parser.add_argument('--symbols', nargs='+', default=['BTC', 'ETH'])

    args = parser.parse_args()

    # Criar diretórios necessários
    Path('logs').mkdir(exist_ok=True)
    Path('state').mkdir(exist_ok=True)
    Path('results').mkdir(exist_ok=True)

    try:
        # Executar ciclo
        cycle = TradingCycle(mode=args.mode)
        results = cycle.run(symbols=args.symbols)

        # Salvar resultados
        results_file = Path(f"results/cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Resultados salvos em {results_file}")

    except Exception as e:
        logger.error(f"Erro fatal no ciclo de trading: {e}", exc_info=True)

        # Notificar erro via Telegram
        notify_error(
            message=str(e),
            error_type="Erro Fatal",
            context=f"Modo: {args.mode}, Símbolos: {args.symbols}"
        )

        raise


if __name__ == '__main__':
    main()
