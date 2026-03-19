"""
Engine de backtest performático.
Suporta múltiplas estratégias e gestão de risco.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from .position import Position, Trade, Side, PortfolioState
from .metrics import calculate_metrics


@dataclass
class BacktestConfig:
    """Configuração do backtest."""
    initial_capital: float = 10000.0
    risk_per_trade: float = 0.02  # 2% por trade
    max_daily_loss: float = 0.05  # 5% máx perda diária
    maker_fee: float = 0.0002  # 0.02%
    taker_fee: float = 0.001  # 0.1%
    slippage: float = 0.0005  # 0.05%
    use_trailing_stop: bool = False
    atr_stop_multiplier: float = 2.0


class BacktestEngine:
    """
    Engine de backtest vetorizado para alta performance.
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.reset()

    def reset(self):
        """Reset do estado."""
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
        self.equity_timestamps: List[datetime] = []
        self.position: Optional[Position] = None
        self.cash = self.config.initial_capital
        self.daily_pnl = 0.0
        self.current_day = None
        self.is_stopped = False

    def run(self,
            data: pd.DataFrame,
            strategy: 'BaseStrategy',
            verbose: bool = False) -> Dict[str, Any]:
        """
        Executa o backtest.

        Args:
            data: DataFrame com colunas ['open', 'high', 'low', 'close', 'volume']
            strategy: Instância da estratégia a testar
            verbose: Se True, printa progresso

        Returns:
            Dict com métricas de performance
        """
        self.reset()

        # Pré-calcular indicadores da estratégia
        strategy.setup(data)

        total_bars = len(data)

        for i in range(strategy.warmup_period, total_bars):
            row = data.iloc[i]
            timestamp = data.index[i]

            # Verificar mudança de dia
            current_date = timestamp.date() if hasattr(timestamp, 'date') else None
            if current_date and current_date != self.current_day:
                self.current_day = current_date
                self.daily_pnl = 0.0
                self.is_stopped = False

            # Skip se stopped por perda diária
            if self.is_stopped:
                self._update_equity(timestamp, row['close'])
                continue

            # Verificar stops da posição atual
            if self.position:
                self._check_stops(row, timestamp)

            # Se não tem posição, verificar entrada
            if not self.position:
                signal = strategy.generate_signal(data, i)
                if signal != 0:
                    self._open_position(
                        timestamp=timestamp,
                        side=Side.LONG if signal > 0 else Side.SHORT,
                        price=row['close'],
                        stop_loss=strategy.get_stop_loss(data, i, signal),
                        take_profit=strategy.get_take_profit(data, i, signal)
                    )

            # Se tem posição, verificar saída por sinal
            elif self.position:
                signal = strategy.generate_signal(data, i)

                # Sinal contrário = fecha posição
                should_close = (
                    (self.position.side == Side.LONG and signal < 0) or
                    (self.position.side == Side.SHORT and signal > 0)
                )

                if should_close:
                    self._close_position(
                        timestamp=timestamp,
                        price=row['close'],
                        reason='signal'
                    )

                # Atualizar trailing stop se configurado
                elif self.config.use_trailing_stop:
                    atr_col = 'atr' if 'atr' in data.columns else None
                    if atr_col:
                        self.position.update_trailing_stop(
                            row['close'],
                            data.iloc[i][atr_col],
                            self.config.atr_stop_multiplier
                        )

            # Atualizar equity curve
            self._update_equity(timestamp, row['close'])

            # Verificar perda diária
            if self.daily_pnl <= -(self.config.initial_capital * self.config.max_daily_loss):
                self.is_stopped = True
                if self.position:
                    self._close_position(timestamp, row['close'], 'daily_stop')

            # Progress
            if verbose and i % 10000 == 0:
                pct = (i / total_bars) * 100
                print(f"Progress: {pct:.1f}%")

        # Fechar posição aberta no final
        if self.position:
            final_row = data.iloc[-1]
            self._close_position(
                timestamp=data.index[-1],
                price=final_row['close'],
                reason='end_of_data'
            )
            self._update_equity(data.index[-1], final_row['close'])

        # Calcular métricas
        equity_series = pd.Series(
            self.equity_curve,
            index=pd.DatetimeIndex(self.equity_timestamps)
        )

        metrics = calculate_metrics(
            self.trades,
            equity_series,
            self.config.initial_capital
        )

        return {
            'metrics': metrics,
            'trades': self.trades,
            'equity_curve': equity_series
        }

    def _open_position(self,
                       timestamp: datetime,
                       side: Side,
                       price: float,
                       stop_loss: Optional[float] = None,
                       take_profit: Optional[float] = None):
        """Abre uma nova posição."""
        # Verificar se tem capital suficiente
        if self.cash < 10:  # Mínimo $10
            return

        # Aplicar slippage
        if side == Side.LONG:
            entry_price = price * (1 + self.config.slippage)
        else:
            entry_price = price * (1 - self.config.slippage)

        # Calcular tamanho baseado no risco (CORRIGIDO)
        # Usar % fixo do capital atual, não baseado em stop distance
        position_value = self.cash * 0.95  # Usar 95% do capital disponível

        # Calcular tamanho em unidades do ativo
        size = position_value / entry_price

        if size <= 0 or size * entry_price < 10:
            return

        # Taxas de entrada
        fee = entry_price * size * self.config.taker_fee

        # Reservar capital para a posição
        self.cash -= (position_value + fee)

        self.position = Position(
            entry_time=timestamp,
            side=side,
            entry_price=entry_price,
            size=size,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    def _close_position(self,
                        timestamp: datetime,
                        price: float,
                        reason: str):
        """Fecha a posição atual."""
        if not self.position:
            return

        # Aplicar slippage
        if self.position.side == Side.LONG:
            exit_price = price * (1 - self.config.slippage)
        else:
            exit_price = price * (1 + self.config.slippage)

        # Calcular PnL
        pnl = self.position.calculate_pnl(exit_price)
        pnl_pct = self.position.calculate_pnl_pct(exit_price)

        # Taxas de saída
        fee = exit_price * self.position.size * self.config.taker_fee
        entry_fee = self.position.entry_price * self.position.size * self.config.taker_fee
        total_fees = fee + entry_fee

        pnl -= total_fees

        # Valor de saída da posição
        exit_value = self.position.size * exit_price

        # Registrar trade
        trade = Trade(
            entry_time=self.position.entry_time,
            exit_time=timestamp,
            side=self.position.side,
            entry_price=self.position.entry_price,
            exit_price=exit_price,
            size=self.position.size,
            pnl=pnl,
            pnl_pct=pnl_pct,
            fees=total_fees,
            exit_reason=reason
        )

        self.trades.append(trade)

        # Atualizar cash: receber valor de saída menos taxas
        self.cash += exit_value - fee
        self.daily_pnl += pnl
        self.position = None

    def _check_stops(self, row: pd.Series, timestamp: datetime):
        """Verifica stop loss e take profit."""
        if not self.position:
            return

        # Check stop loss usando low/high para mais realismo
        if self.position.side == Side.LONG:
            if self.position.stop_loss and row['low'] <= self.position.stop_loss:
                self._close_position(timestamp, self.position.stop_loss, 'sl')
                return
            if self.position.take_profit and row['high'] >= self.position.take_profit:
                self._close_position(timestamp, self.position.take_profit, 'tp')
                return
        else:
            if self.position.stop_loss and row['high'] >= self.position.stop_loss:
                self._close_position(timestamp, self.position.stop_loss, 'sl')
                return
            if self.position.take_profit and row['low'] <= self.position.take_profit:
                self._close_position(timestamp, self.position.take_profit, 'tp')
                return

    def _update_equity(self, timestamp: datetime, current_price: float):
        """Atualiza a curva de equity."""
        if self.position:
            position_value = self.position.size * current_price
            equity = self.cash + position_value
        else:
            equity = self.cash

        # Sanity check - equity não pode ser negativa ou absurdamente alta
        if equity < 0:
            equity = 0
        elif equity > self.config.initial_capital * 1000:  # Max 1000x
            equity = self.config.initial_capital * 1000

        self.equity_curve.append(equity)
        self.equity_timestamps.append(timestamp)


class BaseStrategy:
    """
    Classe base para estratégias.
    Implementar: setup(), generate_signal(), get_stop_loss(), get_take_profit()
    """

    warmup_period: int = 50  # Barras necessárias para indicadores

    def setup(self, data: pd.DataFrame):
        """Pré-calcular indicadores."""
        raise NotImplementedError

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        """
        Gerar sinal de trading.
        Retorna: 1 (long), -1 (short), 0 (neutro)
        """
        raise NotImplementedError

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        """Retorna preço do stop loss."""
        return None

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        """Retorna preço do take profit."""
        return None
