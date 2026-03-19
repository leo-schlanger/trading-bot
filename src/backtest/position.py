"""
Classes para gerenciamento de posições e trades.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class Side(Enum):
    LONG = 1
    SHORT = -1


@dataclass
class Trade:
    """Representa um trade completo (entrada + saída)."""
    entry_time: datetime
    exit_time: datetime
    side: Side
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    fees: float
    exit_reason: str  # 'tp', 'sl', 'signal', 'eod'

    @property
    def duration(self) -> float:
        """Duração do trade em horas."""
        return (self.exit_time - self.entry_time).total_seconds() / 3600

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0


@dataclass
class Position:
    """Posição aberta."""
    entry_time: datetime
    side: Side
    entry_price: float
    size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    def calculate_pnl(self, current_price: float) -> float:
        """Calcula PnL não realizado."""
        if self.side == Side.LONG:
            return (current_price - self.entry_price) * self.size
        else:
            return (self.entry_price - current_price) * self.size

    def calculate_pnl_pct(self, current_price: float) -> float:
        """Calcula PnL % não realizado."""
        if self.side == Side.LONG:
            return (current_price - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - current_price) / self.entry_price

    def should_stop_loss(self, current_price: float) -> bool:
        """Verifica se deve acionar stop loss."""
        if self.stop_loss is None:
            return False

        if self.side == Side.LONG:
            return current_price <= self.stop_loss
        else:
            return current_price >= self.stop_loss

    def should_take_profit(self, current_price: float) -> bool:
        """Verifica se deve acionar take profit."""
        if self.take_profit is None:
            return False

        if self.side == Side.LONG:
            return current_price >= self.take_profit
        else:
            return current_price <= self.take_profit

    def update_trailing_stop(self, current_price: float, atr_value: float, multiplier: float = 2.0):
        """Atualiza trailing stop baseado em ATR."""
        new_stop = None

        if self.side == Side.LONG:
            new_stop = current_price - (atr_value * multiplier)
            if self.stop_loss is None or new_stop > self.stop_loss:
                self.stop_loss = new_stop
        else:
            new_stop = current_price + (atr_value * multiplier)
            if self.stop_loss is None or new_stop < self.stop_loss:
                self.stop_loss = new_stop


@dataclass
class PortfolioState:
    """Estado atual do portfólio."""
    timestamp: datetime
    equity: float
    cash: float
    position_value: float
    unrealized_pnl: float
    realized_pnl: float
    drawdown: float
    drawdown_pct: float
