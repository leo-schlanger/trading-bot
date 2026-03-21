"""
Trading Cycle - Executado a cada 4 horas via GitHub Actions.

Este script:
1. Carrega dados recentes
2. Detecta regime de mercado
3. Seleciona estratégia
4. Verifica sinais
5. Gerencia posições (paper trading com SL/TP)
6. Atualiza capital e P&L
7. Envia notificações
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

# Create directories before logging setup
Path('logs').mkdir(exist_ok=True)
Path('state').mkdir(exist_ok=True)
Path('results').mkdir(exist_ok=True)

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
from src.signals import RegimeSignalGenerator, SignalDirection, SignalStrength

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


class PaperPosition:
    """Representa uma posição aberta em paper trading."""

    def __init__(self, data: Dict[str, Any]):
        self.symbol = data.get('symbol')
        self.direction = data.get('direction')  # 'LONG' or 'SHORT'
        self.entry_price = data.get('entry_price', 0)
        self.entry_time = data.get('entry_time')
        self.size = data.get('size', 0)  # Quantidade do ativo
        self.value = data.get('value', 0)  # Valor em USD
        self.stop_loss = data.get('stop_loss', 0)
        self.take_profit = data.get('take_profit', 0)
        self.regime = data.get('regime')
        self.strategy = data.get('strategy')
        self.signal_confidence = data.get('signal_confidence', 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time,
            'size': self.size,
            'value': self.value,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'regime': self.regime,
            'strategy': self.strategy,
            'signal_confidence': self.signal_confidence
        }

    def check_exit(self, high: float, low: float, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Verifica se a posição deve ser fechada.

        Returns:
            Dict com informações do exit se deve fechar, None caso contrário
        """
        if self.direction == 'LONG':
            # Check stop loss (low touched SL)
            if low <= self.stop_loss:
                return {
                    'reason': 'stop_loss',
                    'exit_price': self.stop_loss,
                    'pnl': (self.stop_loss - self.entry_price) * self.size,
                    'pnl_pct': (self.stop_loss - self.entry_price) / self.entry_price
                }
            # Check take profit (high touched TP)
            if high >= self.take_profit:
                return {
                    'reason': 'take_profit',
                    'exit_price': self.take_profit,
                    'pnl': (self.take_profit - self.entry_price) * self.size,
                    'pnl_pct': (self.take_profit - self.entry_price) / self.entry_price
                }
        else:  # SHORT
            # Check stop loss (high touched SL)
            if high >= self.stop_loss:
                return {
                    'reason': 'stop_loss',
                    'exit_price': self.stop_loss,
                    'pnl': (self.entry_price - self.stop_loss) * self.size,
                    'pnl_pct': (self.entry_price - self.stop_loss) / self.entry_price
                }
            # Check take profit (low touched TP)
            if low <= self.take_profit:
                return {
                    'reason': 'take_profit',
                    'exit_price': self.take_profit,
                    'pnl': (self.entry_price - self.take_profit) * self.size,
                    'pnl_pct': (self.entry_price - self.take_profit) / self.entry_price
                }

        return None

    def close_at_price(self, price: float, reason: str = 'signal') -> Dict[str, Any]:
        """Fecha a posição ao preço especificado."""
        if self.direction == 'LONG':
            pnl = (price - self.entry_price) * self.size
            pnl_pct = (price - self.entry_price) / self.entry_price
        else:  # SHORT
            pnl = (self.entry_price - price) * self.size
            pnl_pct = (self.entry_price - price) / self.entry_price

        return {
            'reason': reason,
            'exit_price': price,
            'pnl': pnl,
            'pnl_pct': pnl_pct
        }


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
        self.signal_generator = RegimeSignalGenerator()

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
                    state = json.load(f)
                    # Migração: converter positions antigo para novo formato
                    if 'position' in state and state['position'] is None:
                        if 'positions' not in state:
                            state['positions'] = {}
                    return state
            except Exception as e:
                logger.warning(f"Erro ao carregar estado: {e}")

        return {
            'capital': 500.0,
            'positions': {},  # {symbol: position_data}
            'last_regime': None,
            'consecutive_losses': 0,
            'consecutive_wins': 0,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'decision_log': [],
            'last_signals': {},
            'trade_history': []  # Histórico completo de trades fechados
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

    def _check_open_positions(self, df: pd.DataFrame, symbol: str) -> List[Dict[str, Any]]:
        """
        Verifica posições abertas e fecha se SL/TP foi atingido.

        Returns:
            Lista de trades fechados
        """
        closed_trades = []
        positions = self.state.get('positions', {})

        if symbol not in positions:
            return closed_trades

        position_data = positions[symbol]
        position = PaperPosition(position_data)

        # Pegar candles desde a entrada da posição
        entry_time = pd.to_datetime(position.entry_time)

        # Filtrar candles após a entrada
        recent_candles = df[df.index > entry_time]

        if recent_candles.empty:
            # Verificar só o candle atual
            recent_candles = df.tail(1)

        # Verificar cada candle para SL/TP
        for idx, candle in recent_candles.iterrows():
            exit_info = position.check_exit(
                high=candle['high'],
                low=candle['low'],
                current_price=candle['close']
            )

            if exit_info:
                # Fechar posição
                trade_record = self._close_position(symbol, position, exit_info, idx)
                closed_trades.append(trade_record)
                break

        return closed_trades

    def _close_position(self, symbol: str, position: PaperPosition,
                        exit_info: Dict[str, Any], exit_time) -> Dict[str, Any]:
        """Fecha uma posição e atualiza o estado."""
        pnl = exit_info['pnl']
        pnl_pct = exit_info['pnl_pct']

        # Atualizar capital
        self.state['capital'] += pnl
        self.state['total_pnl'] += pnl
        self.state['total_trades'] += 1

        # Atualizar contadores de win/loss
        if pnl > 0:
            self.state['winning_trades'] = self.state.get('winning_trades', 0) + 1
            self.state['consecutive_wins'] = self.state.get('consecutive_wins', 0) + 1
            self.state['consecutive_losses'] = 0
        else:
            self.state['losing_trades'] = self.state.get('losing_trades', 0) + 1
            self.state['consecutive_losses'] = self.state.get('consecutive_losses', 0) + 1
            self.state['consecutive_wins'] = 0

        # Atualizar risk manager
        self.risk_manager.state.current_capital = self.state['capital']
        if self.state['capital'] > self.risk_manager.state.peak_capital:
            self.risk_manager.state.peak_capital = self.state['capital']
        self.risk_manager.state.consecutive_losses = self.state['consecutive_losses']

        # Criar registro do trade
        trade_record = {
            'symbol': symbol,
            'direction': position.direction,
            'entry_price': position.entry_price,
            'entry_time': position.entry_time,
            'exit_price': exit_info['exit_price'],
            'exit_time': str(exit_time),
            'exit_reason': exit_info['reason'],
            'size': position.size,
            'value': position.value,
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct * 100, 2),
            'regime': position.regime,
            'strategy': position.strategy,
            'stop_loss': position.stop_loss,
            'take_profit': position.take_profit
        }

        # Adicionar ao histórico
        if 'trade_history' not in self.state:
            self.state['trade_history'] = []
        self.state['trade_history'].append(trade_record)

        # Remover posição
        del self.state['positions'][symbol]

        logger.info(f"FECHOU {position.direction} {symbol} @ ${exit_info['exit_price']:.2f} "
                   f"| Razão: {exit_info['reason']} | P&L: ${pnl:.2f} ({pnl_pct*100:.2f}%)")

        return trade_record

    def _open_position(self, symbol: str, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Abre uma nova posição."""
        details = analysis.get('details', {})

        if 'sizing' not in details:
            return None

        # Verificar se já tem posição neste símbolo
        if symbol in self.state.get('positions', {}):
            logger.warning(f"Já existe posição aberta em {symbol}, ignorando novo sinal")
            return None

        position_data = {
            'symbol': symbol,
            'direction': analysis['action'],
            'entry_price': details['price'],
            'entry_time': analysis['timestamp'],
            'size': details['sizing'].get('position_size', 0),
            'value': details['sizing'].get('position_value', 0),
            'stop_loss': details['stop_loss'],
            'take_profit': details['take_profit'],
            'regime': analysis['regime'],
            'strategy': analysis.get('strategy'),
            'signal_confidence': details.get('signal_confidence', 0)
        }

        # Salvar posição
        if 'positions' not in self.state:
            self.state['positions'] = {}
        self.state['positions'][symbol] = position_data

        logger.info(f"ABRIU {analysis['action']} {symbol} @ ${details['price']:.2f} "
                   f"| SL: ${details['stop_loss']:.2f} | TP: ${details['take_profit']:.2f} "
                   f"| Size: ${position_data['value']:.2f}")

        return position_data

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

        # 4. Gerar sinal usando RegimeSignalGenerator (2026 best practices)
        trade_signal = self.signal_generator.generate_signal(df, regime.value)

        result['details']['signal_strength'] = trade_signal.strength.name
        result['details']['signal_confidence'] = trade_signal.confidence
        result['details']['signal_reasons'] = trade_signal.reasons
        result['details']['signal_strategy'] = trade_signal.strategy
        result['details']['traps_detected'] = trade_signal.traps_detected
        result['details']['trap_warning'] = trade_signal.trap_warning

        if trade_signal.direction == SignalDirection.LONG:
            result['signal'] = 1
            result['action'] = 'LONG'
        elif trade_signal.direction == SignalDirection.SHORT:
            result['signal'] = -1
            result['action'] = 'SHORT'
        else:
            result['signal'] = 0
            result['action'] = 'HOLD'

        # 5. Calcular position size se houver sinal
        if result['signal'] != 0:
            close = df['close'].iloc[-1]

            # Usar ATR multipliers do signal para stops e targets
            stop_distance = current_atr * trade_signal.stop_multiplier
            target_distance = current_atr * trade_signal.target_multiplier

            if result['signal'] > 0:  # LONG
                stop_loss = close - stop_distance
                take_profit = close + target_distance
            else:  # SHORT
                stop_loss = close + stop_distance
                take_profit = close - target_distance

            # Position sizing do risk manager ajustado pelo signal
            sizing = self.risk_manager.get_position_size(regime, close, stop_loss)

            # Aplicar multiplicadores: safety + signal confidence
            position_multiplier = safety_result.get('position_multiplier', 1.0)
            position_multiplier *= trade_signal.position_size_pct

            sizing['position_value'] *= position_multiplier
            sizing['signal_position_pct'] = trade_signal.position_size_pct

            result['details']['sizing'] = sizing
            result['details']['price'] = close
            result['details']['stop_loss'] = stop_loss
            result['details']['take_profit'] = take_profit
            result['details']['stop_atr_mult'] = trade_signal.stop_multiplier
            result['details']['target_atr_mult'] = trade_signal.target_multiplier

        return result

    def execute(self, df: pd.DataFrame, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Executa a ação recomendada."""
        result = {
            'executed': False,
            'action': analysis['action'],
            'mode': self.mode,
            'details': {},
            'closed_trades': [],
            'opened_position': None
        }

        symbol = analysis['symbol']

        # 1. Primeiro, verificar posições abertas para SL/TP
        closed_trades = self._check_open_positions(df, symbol)
        result['closed_trades'] = closed_trades

        if closed_trades:
            for trade in closed_trades:
                logger.info(f"Trade fechado: {trade['direction']} {trade['symbol']} "
                           f"| P&L: ${trade['pnl']:.2f}")

        # 2. Se ação é HOLD, SKIP ou BLOCKED, não faz mais nada
        if analysis['action'] in ['HOLD', 'SKIP', 'BLOCKED']:
            logger.info(f"Nenhuma ação: {analysis['action']}")
            return result

        # 3. Se já tem posição neste símbolo, verificar se deve fechar por sinal oposto
        positions = self.state.get('positions', {})
        if symbol in positions:
            current_pos = positions[symbol]

            # Se sinal é oposto, fechar posição atual
            if (current_pos['direction'] == 'LONG' and analysis['action'] == 'SHORT') or \
               (current_pos['direction'] == 'SHORT' and analysis['action'] == 'LONG'):

                current_price = analysis['details'].get('price', df['close'].iloc[-1])
                position = PaperPosition(current_pos)
                exit_info = position.close_at_price(current_price, 'opposite_signal')
                trade_record = self._close_position(symbol, position, exit_info, datetime.now())
                result['closed_trades'].append(trade_record)
                logger.info(f"Fechou posição por sinal oposto")
            else:
                # Mesmo sinal, já está posicionado
                logger.info(f"Já posicionado {current_pos['direction']} em {symbol}, mantendo")
                return result

        # 4. Log signal details para LONG/SHORT
        if analysis['action'] in ['LONG', 'SHORT']:
            details = analysis.get('details', {})
            logger.info(f"Signal: {analysis['action']} | "
                       f"Strength: {details.get('signal_strength', 'N/A')} | "
                       f"Confidence: {details.get('signal_confidence', 0):.2f} | "
                       f"Reasons: {', '.join(details.get('signal_reasons', []))}")

        # 5. Executar baseado no modo
        if self.mode == 'backtest':
            logger.info("Modo backtest - simulando execução")
            result['executed'] = True
            result['details']['simulated'] = True

        elif self.mode == 'paper':
            logger.info("Modo paper trading - abrindo posição simulada")

            # Abrir nova posição
            opened = self._open_position(symbol, analysis)
            if opened:
                result['executed'] = True
                result['opened_position'] = opened
                result['details']['paper_trade'] = True

        elif self.mode == 'live':
            logger.info("Modo LIVE - executando trade real")
            # TODO: Integrar com exchange API
            logger.warning("Execução live não implementada ainda")

        return result

    def _log_decision(self, analysis: Dict[str, Any]):
        """Registra decisão para o dashboard."""
        details = analysis.get('details', {})

        decision = {
            'timestamp': analysis['timestamp'],
            'symbol': analysis['symbol'],
            'action': analysis['action'],
            'regime': analysis['regime'],
            'confidence': details.get('signal_confidence', 0),
            'strength': details.get('signal_strength', 'N/A'),
            'reasons': details.get('signal_reasons', []),
            'strategy': analysis.get('strategy'),
            'price': details.get('price'),
            'stop_loss': details.get('stop_loss'),
            'take_profit': details.get('take_profit'),
            'traps_detected': details.get('traps_detected', []),
            'trap_warning': details.get('trap_warning', False)
        }

        # Adicionar ao log de decisões
        if 'decision_log' not in self.state:
            self.state['decision_log'] = []
        self.state['decision_log'].append(decision)

        # Manter apenas últimas 100 decisões
        if len(self.state['decision_log']) > 100:
            self.state['decision_log'] = self.state['decision_log'][-100:]

        # Salvar última decisão por símbolo
        if 'last_signals' not in self.state:
            self.state['last_signals'] = {}
        self.state['last_signals'][analysis['symbol']] = decision

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

    def _get_portfolio_summary(self) -> Dict[str, Any]:
        """Retorna resumo do portfólio."""
        positions = self.state.get('positions', {})
        trade_history = self.state.get('trade_history', [])

        # Calcular win rate
        total_closed = len(trade_history)
        winning = sum(1 for t in trade_history if t.get('pnl', 0) > 0)
        win_rate = winning / total_closed if total_closed > 0 else 0

        # Calcular profit factor
        gross_profit = sum(t['pnl'] for t in trade_history if t.get('pnl', 0) > 0)
        gross_loss = abs(sum(t['pnl'] for t in trade_history if t.get('pnl', 0) < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

        # Valor em posições abertas
        open_value = sum(p.get('value', 0) for p in positions.values())

        return {
            'capital': self.state.get('capital', 500.0),
            'total_pnl': self.state.get('total_pnl', 0),
            'total_trades': total_closed,
            'winning_trades': winning,
            'losing_trades': total_closed - winning,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'open_positions': len(positions),
            'open_value': open_value,
            'consecutive_losses': self.state.get('consecutive_losses', 0),
            'consecutive_wins': self.state.get('consecutive_wins', 0)
        }

    def run(self, symbols: list = None):
        """Executa ciclo completo de trading."""
        symbols = symbols or ['BTC', 'ETH']

        logger.info("=" * 50)
        logger.info(f"Iniciando ciclo de trading - {datetime.now()}")
        logger.info(f"Modo: {self.mode}")
        logger.info(f"Símbolos: {symbols}")
        logger.info(f"Capital: ${self.state.get('capital', 500.0):.2f}")
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

            # Executar (inclui verificação de SL/TP)
            execution = self.execute(df, analysis)

            # Registrar decisão para dashboard
            self._log_decision(analysis)

            # Notificar (apenas para sinais ativos: LONG, SHORT, BLOCKED)
            if analysis['action'] in ['LONG', 'SHORT', 'BLOCKED']:
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

        # Salvar último regime de cada símbolo analisado
        for r in results:
            if r['analysis'].get('regime'):
                self.state['last_regime'] = r['analysis']['regime']
                break

        self._save_state()

        # Resumo
        portfolio = self._get_portfolio_summary()
        logger.info("\n" + "=" * 50)
        logger.info("RESUMO DO CICLO")
        logger.info("=" * 50)
        logger.info(f"Capital: ${portfolio['capital']:.2f} | P&L Total: ${portfolio['total_pnl']:.2f}")
        logger.info(f"Trades: {portfolio['total_trades']} | Win Rate: {portfolio['win_rate']*100:.1f}%")
        logger.info(f"Posições Abertas: {portfolio['open_positions']}")

        for r in results:
            analysis = r['analysis']
            execution = r['execution']
            details = analysis.get('details', {})
            action = analysis['action']
            regime = analysis['regime']

            if action in ['LONG', 'SHORT']:
                strength = details.get('signal_strength', 'N/A')
                conf = details.get('signal_confidence', 0)
                price = details.get('price', 0)
                stop = details.get('stop_loss', 0)
                target = details.get('take_profit', 0)
                logger.info(f"{r['symbol']}: {action} | Regime: {regime} | "
                           f"Strength: {strength} | Confidence: {conf:.2f}")
                logger.info(f"  Price: ${price:.2f} | Stop: ${stop:.2f} | Target: ${target:.2f}")

                if execution.get('closed_trades'):
                    for ct in execution['closed_trades']:
                        logger.info(f"  FECHOU: {ct['exit_reason']} | P&L: ${ct['pnl']:.2f}")
            else:
                logger.info(f"{r['symbol']}: {action} ({regime})")

                if execution.get('closed_trades'):
                    for ct in execution['closed_trades']:
                        logger.info(f"  FECHOU: {ct['exit_reason']} | P&L: ${ct['pnl']:.2f}")

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
