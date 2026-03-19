"""
Risk Manager for intelligent trading bot.

Implements:
- Half-Kelly position sizing
- Per-regime risk adjustments
- Drawdown monitoring
- Daily loss limits
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import logging

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/src/', 1)[0])

from src.ml.regime_detector import MarketRegime


@dataclass
class RiskConfig:
    """Risk management configuration for $500 capital."""
    # Capital limits
    initial_capital: float = 500.0
    max_position_pct: float = 0.95  # 95% = $475 max position
    min_position_pct: float = 0.10  # 10% = $50 min position

    # Risk per trade
    base_risk_per_trade: float = 0.02  # 2% = $10 base risk
    max_risk_per_trade: float = 0.03   # 3% max
    min_risk_per_trade: float = 0.01   # 1% min

    # Drawdown limits
    max_daily_loss_pct: float = 0.05   # 5% = $25 daily limit
    max_total_drawdown_pct: float = 0.20  # 20% = stop at $400

    # Kelly criterion
    kelly_fraction: float = 0.5  # Half-Kelly (conservative)

    # Per-regime adjustments
    regime_position_multipliers: Dict[str, float] = field(default_factory=lambda: {
        'bull': 0.80,       # 80% of max in bull
        'bear': 0.50,       # 50% of max in bear
        'sideways': 0.60,   # 60% of max in sideways
        'correction': 0.30  # 30% of max in correction
    })

    regime_risk_multipliers: Dict[str, float] = field(default_factory=lambda: {
        'bull': 1.5,        # 3% risk in bull (1.5 * 2%)
        'bear': 1.0,        # 2% risk in bear
        'sideways': 1.0,    # 2% risk in sideways
        'correction': 0.5   # 1% risk in correction
    })


@dataclass
class RiskState:
    """Current risk state tracking."""
    current_capital: float
    peak_capital: float
    daily_pnl: float
    total_drawdown: float
    daily_trades: int
    daily_losses: int
    consecutive_losses: int
    last_trade_date: Optional[date] = None
    is_trading_allowed: bool = True
    stop_reason: Optional[str] = None


class RiskManager:
    """
    Comprehensive risk management system.

    Features:
    - Dynamic position sizing based on Kelly criterion
    - Regime-aware risk adjustments
    - Drawdown monitoring and circuit breakers
    - Daily loss tracking
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self.state = RiskState(
            current_capital=self.config.initial_capital,
            peak_capital=self.config.initial_capital,
            daily_pnl=0.0,
            total_drawdown=0.0,
            daily_trades=0,
            daily_losses=0,
            consecutive_losses=0
        )
        self.trade_history: List[Dict] = []
        self.logger = logging.getLogger(__name__)

    def calculate_kelly_fraction(self,
                                  win_rate: float,
                                  avg_win: float,
                                  avg_loss: float) -> float:
        """
        Calculate Kelly criterion position fraction.

        Kelly % = W - [(1-W) / R]
        Where W = win rate, R = win/loss ratio

        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade size
            avg_loss: Average losing trade size (positive number)

        Returns:
            Recommended position fraction (0-1)
        """
        if avg_loss <= 0 or win_rate <= 0:
            return 0.0

        win_loss_ratio = avg_win / avg_loss

        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        # Apply half-Kelly for conservatism
        kelly *= self.config.kelly_fraction

        # Clamp to reasonable bounds
        return max(0.0, min(kelly, 0.25))  # Max 25% of capital

    def get_position_size(self,
                          regime: MarketRegime,
                          current_price: float,
                          stop_loss_price: float,
                          win_rate: Optional[float] = None,
                          avg_win_loss: Optional[Tuple[float, float]] = None) -> Dict[str, float]:
        """
        Calculate recommended position size.

        Args:
            regime: Current market regime
            current_price: Current asset price
            stop_loss_price: Stop loss price
            win_rate: Historical win rate (optional)
            avg_win_loss: Tuple of (avg_win, avg_loss) (optional)

        Returns:
            Dict with position sizing details
        """
        if not self.state.is_trading_allowed:
            return {
                'position_size': 0,
                'position_value': 0,
                'risk_amount': 0,
                'reason': self.state.stop_reason or 'Trading not allowed'
            }

        # Get regime multipliers
        regime_pos_mult = self.config.regime_position_multipliers.get(
            regime.value, 0.5
        )
        regime_risk_mult = self.config.regime_risk_multipliers.get(
            regime.value, 1.0
        )

        # Calculate risk per trade
        adjusted_risk_pct = self.config.base_risk_per_trade * regime_risk_mult
        adjusted_risk_pct = max(
            self.config.min_risk_per_trade,
            min(adjusted_risk_pct, self.config.max_risk_per_trade)
        )

        risk_amount = self.state.current_capital * adjusted_risk_pct

        # Calculate position based on stop loss distance
        stop_distance_pct = abs(current_price - stop_loss_price) / current_price
        if stop_distance_pct <= 0:
            stop_distance_pct = 0.02  # Default 2% if not specified

        # Position value based on risk
        position_value_risk_based = risk_amount / stop_distance_pct

        # Maximum position based on regime
        max_position_value = (
            self.state.current_capital *
            self.config.max_position_pct *
            regime_pos_mult
        )

        # Apply Kelly if statistics provided
        if win_rate and avg_win_loss:
            kelly_frac = self.calculate_kelly_fraction(
                win_rate, avg_win_loss[0], avg_win_loss[1]
            )
            kelly_position = self.state.current_capital * kelly_frac
            # Use minimum of Kelly and risk-based
            position_value = min(position_value_risk_based, kelly_position, max_position_value)
        else:
            position_value = min(position_value_risk_based, max_position_value)

        # Ensure minimum position
        min_position_value = self.state.current_capital * self.config.min_position_pct
        if position_value < min_position_value:
            position_value = 0  # Skip trade if too small

        # Calculate number of units
        position_size = position_value / current_price if current_price > 0 else 0

        return {
            'position_size': position_size,
            'position_value': position_value,
            'risk_amount': risk_amount,
            'risk_pct': adjusted_risk_pct,
            'max_allowed': max_position_value,
            'regime_adjustment': regime_pos_mult,
            'stop_distance_pct': stop_distance_pct
        }

    def check_daily_limits(self) -> Tuple[bool, Optional[str]]:
        """
        Check if daily limits have been exceeded.

        Returns:
            Tuple of (can_trade, reason_if_not)
        """
        today = date.today()

        # Reset daily stats if new day
        if self.state.last_trade_date != today:
            self.state.daily_pnl = 0.0
            self.state.daily_trades = 0
            self.state.daily_losses = 0
            self.state.last_trade_date = today

        # Check daily loss limit
        daily_loss_limit = self.config.initial_capital * self.config.max_daily_loss_pct

        if self.state.daily_pnl < -daily_loss_limit:
            return False, f"Daily loss limit reached: ${abs(self.state.daily_pnl):.2f}"

        return True, None

    def check_drawdown_limit(self) -> Tuple[bool, Optional[str]]:
        """
        Check if maximum drawdown has been exceeded.

        Returns:
            Tuple of (can_trade, reason_if_not)
        """
        drawdown_pct = (
            (self.state.peak_capital - self.state.current_capital) /
            self.state.peak_capital
        )

        if drawdown_pct >= self.config.max_total_drawdown_pct:
            self.state.is_trading_allowed = False
            self.state.stop_reason = f"Max drawdown reached: {drawdown_pct*100:.1f}%"
            return False, self.state.stop_reason

        return True, None

    def can_trade(self, regime: MarketRegime) -> Tuple[bool, Optional[str]]:
        """
        Comprehensive check if trading is allowed.

        Args:
            regime: Current market regime

        Returns:
            Tuple of (can_trade, reason_if_not)
        """
        # Check if globally stopped
        if not self.state.is_trading_allowed:
            return False, self.state.stop_reason

        # Check daily limits
        daily_ok, daily_reason = self.check_daily_limits()
        if not daily_ok:
            return False, daily_reason

        # Check drawdown
        dd_ok, dd_reason = self.check_drawdown_limit()
        if not dd_ok:
            return False, dd_reason

        # All checks passed
        return True, None

    def update_on_trade(self, pnl: float, is_win: bool) -> None:
        """
        Update state after a trade completes.

        Args:
            pnl: Profit/loss from the trade
            is_win: Whether the trade was profitable
        """
        self.state.current_capital += pnl
        self.state.daily_pnl += pnl
        self.state.daily_trades += 1

        # Track consecutive losses
        if is_win:
            self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses += 1
            self.state.daily_losses += 1

        # Update peak capital
        if self.state.current_capital > self.state.peak_capital:
            self.state.peak_capital = self.state.current_capital

        # Update total drawdown
        self.state.total_drawdown = (
            self.state.peak_capital - self.state.current_capital
        )

        # Record trade
        self.trade_history.append({
            'timestamp': datetime.now(),
            'pnl': pnl,
            'is_win': is_win,
            'capital_after': self.state.current_capital,
            'drawdown': self.state.total_drawdown,
            'consecutive_losses': self.state.consecutive_losses
        })

        self.logger.info(
            f"Trade completed: PnL=${pnl:.2f}, Capital=${self.state.current_capital:.2f}, "
            f"Drawdown=${self.state.total_drawdown:.2f}"
        )

    def get_risk_metrics(self) -> Dict[str, float]:
        """Get current risk metrics."""
        return {
            'current_capital': self.state.current_capital,
            'peak_capital': self.state.peak_capital,
            'total_drawdown': self.state.total_drawdown,
            'drawdown_pct': (
                self.state.total_drawdown / self.state.peak_capital * 100
                if self.state.peak_capital > 0 else 0
            ),
            'daily_pnl': self.state.daily_pnl,
            'daily_pnl_pct': (
                self.state.daily_pnl / self.config.initial_capital * 100
            ),
            'consecutive_losses': self.state.consecutive_losses,
            'total_trades': len(self.trade_history),
            'is_trading_allowed': self.state.is_trading_allowed
        }

    def get_trade_statistics(self) -> Dict[str, float]:
        """Calculate statistics from trade history."""
        if not self.trade_history:
            return {
                'win_rate': 0.5,  # Default assumption
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 1.0
            }

        wins = [t['pnl'] for t in self.trade_history if t['is_win']]
        losses = [abs(t['pnl']) for t in self.trade_history if not t['is_win']]

        win_rate = len(wins) / len(self.trade_history) if self.trade_history else 0.5
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0

        gross_profit = sum(wins)
        gross_loss = sum(losses)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 1.0

        return {
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_wins': len(wins),
            'total_losses': len(losses),
            'gross_profit': gross_profit,
            'gross_loss': gross_loss
        }

    def reset_daily(self) -> None:
        """Reset daily counters (call at start of new trading day)."""
        self.state.daily_pnl = 0.0
        self.state.daily_trades = 0
        self.state.daily_losses = 0
        self.state.last_trade_date = date.today()

    def reset_all(self, new_capital: Optional[float] = None) -> None:
        """Reset all state (for backtesting or restart)."""
        capital = new_capital or self.config.initial_capital
        self.state = RiskState(
            current_capital=capital,
            peak_capital=capital,
            daily_pnl=0.0,
            total_drawdown=0.0,
            daily_trades=0,
            daily_losses=0,
            consecutive_losses=0
        )
        self.trade_history = []

    def emergency_stop(self, reason: str) -> None:
        """Immediately stop all trading."""
        self.state.is_trading_allowed = False
        self.state.stop_reason = reason
        self.logger.critical(f"EMERGENCY STOP: {reason}")

    def resume_trading(self) -> None:
        """Resume trading after manual review."""
        self.state.is_trading_allowed = True
        self.state.stop_reason = None
        self.logger.info("Trading resumed")
