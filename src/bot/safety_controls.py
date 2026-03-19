"""
Safety Controls and Circuit Breakers for the intelligent trading bot.

Implements protective mechanisms:
- Consecutive loss limits
- Daily loss limits
- Maximum drawdown stops
- Volatility-based position reduction
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
import logging

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/src/', 1)[0])

from src.ml.regime_detector import MarketRegime


class CircuitBreakerType(Enum):
    """Types of circuit breakers."""
    CONSECUTIVE_LOSSES = "consecutive_losses"
    DAILY_LOSS = "daily_loss"
    TOTAL_DRAWDOWN = "total_drawdown"
    HIGH_VOLATILITY = "high_volatility"
    MANUAL_STOP = "manual_stop"
    REGIME_CHANGE = "regime_change"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breakers."""
    # Capital (required for percentage calculations)
    initial_capital: float = 500.0

    # Consecutive losses
    max_consecutive_losses: int = 3
    consecutive_loss_pause_hours: int = 24

    # Daily loss
    max_daily_loss_pct: float = 0.05  # 5%
    daily_loss_reset_hour: int = 0    # UTC hour to reset

    # Total drawdown
    max_total_drawdown_pct: float = 0.20  # 20%
    drawdown_resume_threshold: float = 0.15  # Resume at 15% DD

    # Volatility
    high_volatility_threshold: float = 2.0  # 2x average ATR
    volatility_position_reduction: float = 0.5  # 50% reduction

    # Regime change
    pause_on_regime_change: bool = True
    regime_change_pause_bars: int = 2


@dataclass
class CircuitBreaker:
    """Represents an active circuit breaker."""
    breaker_type: CircuitBreakerType
    triggered_at: datetime
    reason: str
    severity: str  # 'warning', 'critical', 'emergency'
    resume_condition: Optional[str] = None
    auto_resume_at: Optional[datetime] = None


@dataclass
class SafetyState:
    """Current safety system state."""
    is_trading_allowed: bool = True
    position_size_multiplier: float = 1.0
    active_breakers: List[CircuitBreaker] = field(default_factory=list)
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_losses: int = 0
    consecutive_losses: int = 0
    total_drawdown_pct: float = 0.0
    current_volatility_ratio: float = 1.0
    last_regime: Optional[MarketRegime] = None
    bars_since_regime_change: int = 0
    last_trade_date: Optional[date] = None


class SafetyControls:
    """
    Comprehensive safety control system.

    Features:
    - Multiple circuit breakers
    - Automatic position reduction
    - Pause/resume mechanisms
    - Detailed logging
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.state = SafetyState()
        self.event_log: List[Dict] = []
        self.callbacks: Dict[str, List[Callable]] = {
            'on_breaker_triggered': [],
            'on_breaker_cleared': [],
            'on_trading_stopped': [],
            'on_trading_resumed': []
        }
        self.logger = logging.getLogger(__name__)

    def check_all(self,
                  regime: MarketRegime,
                  current_atr: float,
                  avg_atr: float) -> Dict[str, Any]:
        """
        Run all safety checks.

        Args:
            regime: Current market regime
            current_atr: Current ATR value
            avg_atr: Average ATR value

        Returns:
            Dict with check results and recommendations
        """
        results = {
            'can_trade': True,
            'position_multiplier': 1.0,
            'warnings': [],
            'blockers': [],
            'active_breakers': []
        }

        # Check consecutive losses
        self._check_consecutive_losses(results)

        # Check daily loss
        self._check_daily_loss(results)

        # Check total drawdown
        self._check_total_drawdown(results)

        # Check volatility
        self._check_volatility(results, current_atr, avg_atr)

        # Check regime change
        self._check_regime_change(results, regime)

        # Check auto-resume for timed breakers
        self._check_auto_resume()

        # Update state
        self.state.is_trading_allowed = results['can_trade']
        self.state.position_size_multiplier = results['position_multiplier']
        self.state.active_breakers = [b for b in self.state.active_breakers
                                       if b in results.get('active_breakers_objs', [])]

        return results

    def _check_consecutive_losses(self, results: Dict) -> None:
        """Check consecutive loss limit."""
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            breaker = self._get_or_create_breaker(
                CircuitBreakerType.CONSECUTIVE_LOSSES,
                f"{self.state.consecutive_losses} consecutive losses",
                'warning'
            )

            # Set auto-resume time
            if breaker.auto_resume_at is None:
                breaker.auto_resume_at = datetime.now() + timedelta(
                    hours=self.config.consecutive_loss_pause_hours
                )
                breaker.resume_condition = f"Auto-resume at {breaker.auto_resume_at}"

            results['warnings'].append(
                f"Consecutive loss limit ({self.config.max_consecutive_losses}) reached"
            )
            results['blockers'].append(breaker.reason)
            results['can_trade'] = False
            results['active_breakers'].append(breaker.breaker_type.value)

    def _check_daily_loss(self, results: Dict) -> None:
        """Check daily loss limit."""
        # Reset daily stats if new day
        today = date.today()
        if self.state.last_trade_date != today:
            self.state.daily_pnl = 0.0
            self.state.daily_trades = 0
            self.state.daily_losses = 0
            self.state.last_trade_date = today
            # Clear daily loss breaker if exists
            self._clear_breaker(CircuitBreakerType.DAILY_LOSS)

        daily_loss_pct = abs(min(0, self.state.daily_pnl)) / self.config.initial_capital
        if daily_loss_pct >= self.config.max_daily_loss_pct:
            breaker = self._get_or_create_breaker(
                CircuitBreakerType.DAILY_LOSS,
                f"Daily loss {daily_loss_pct*100:.1f}% exceeds {self.config.max_daily_loss_pct*100}% limit",
                'critical'
            )

            results['blockers'].append(breaker.reason)
            results['can_trade'] = False
            results['active_breakers'].append(breaker.breaker_type.value)

    def _check_total_drawdown(self, results: Dict) -> None:
        """Check total drawdown limit."""
        if self.state.total_drawdown_pct >= self.config.max_total_drawdown_pct:
            breaker = self._get_or_create_breaker(
                CircuitBreakerType.TOTAL_DRAWDOWN,
                f"Total drawdown {self.state.total_drawdown_pct*100:.1f}% exceeds {self.config.max_total_drawdown_pct*100}% limit",
                'emergency'
            )
            breaker.resume_condition = f"Manual review required. Resume when DD < {self.config.drawdown_resume_threshold*100}%"

            results['blockers'].append(breaker.reason)
            results['can_trade'] = False
            results['active_breakers'].append(breaker.breaker_type.value)

    def _check_volatility(self,
                          results: Dict,
                          current_atr: float,
                          avg_atr: float) -> None:
        """Check volatility and adjust position size."""
        if avg_atr <= 0:
            return

        vol_ratio = current_atr / avg_atr
        self.state.current_volatility_ratio = vol_ratio

        if vol_ratio >= self.config.high_volatility_threshold:
            # Don't block trading, but reduce position size
            reduction = self.config.volatility_position_reduction
            results['position_multiplier'] *= reduction

            results['warnings'].append(
                f"High volatility ({vol_ratio:.1f}x avg) - position reduced to {reduction*100}%"
            )

            # Create warning breaker (doesn't block)
            self._get_or_create_breaker(
                CircuitBreakerType.HIGH_VOLATILITY,
                f"Volatility {vol_ratio:.1f}x average",
                'warning'
            )
            results['active_breakers'].append(CircuitBreakerType.HIGH_VOLATILITY.value)
        else:
            # Clear volatility breaker
            self._clear_breaker(CircuitBreakerType.HIGH_VOLATILITY)

    def _check_regime_change(self, results: Dict, regime: MarketRegime) -> None:
        """Check for regime change and apply pause if configured."""
        if not self.config.pause_on_regime_change:
            return

        if self.state.last_regime is not None and regime != self.state.last_regime:
            self.state.bars_since_regime_change = 0
            self._get_or_create_breaker(
                CircuitBreakerType.REGIME_CHANGE,
                f"Regime changed from {self.state.last_regime.value} to {regime.value}",
                'warning'
            )
            self.logger.info(f"Regime change detected: {self.state.last_regime.value} -> {regime.value}")

        self.state.last_regime = regime

        if self.state.bars_since_regime_change < self.config.regime_change_pause_bars:
            results['warnings'].append(
                f"Recent regime change - waiting {self.config.regime_change_pause_bars - self.state.bars_since_regime_change} more bars"
            )
            results['can_trade'] = False
            results['active_breakers'].append(CircuitBreakerType.REGIME_CHANGE.value)
        else:
            self._clear_breaker(CircuitBreakerType.REGIME_CHANGE)

    def _check_auto_resume(self) -> None:
        """Check and process auto-resume for timed breakers."""
        now = datetime.now()

        for breaker in self.state.active_breakers[:]:  # Copy list for safe iteration
            if breaker.auto_resume_at and now >= breaker.auto_resume_at:
                self._clear_breaker(breaker.breaker_type)
                self._log_event('auto_resume', f"Auto-resumed after {breaker.breaker_type.value}")

    def _get_or_create_breaker(self,
                               breaker_type: CircuitBreakerType,
                               reason: str,
                               severity: str) -> CircuitBreaker:
        """Get existing breaker or create new one."""
        for breaker in self.state.active_breakers:
            if breaker.breaker_type == breaker_type:
                return breaker

        breaker = CircuitBreaker(
            breaker_type=breaker_type,
            triggered_at=datetime.now(),
            reason=reason,
            severity=severity
        )
        self.state.active_breakers.append(breaker)

        # Log and callback
        self._log_event('breaker_triggered', f"{breaker_type.value}: {reason}")
        self._trigger_callbacks('on_breaker_triggered', breaker)

        return breaker

    def _clear_breaker(self, breaker_type: CircuitBreakerType) -> None:
        """Clear a specific breaker."""
        for breaker in self.state.active_breakers[:]:
            if breaker.breaker_type == breaker_type:
                self.state.active_breakers.remove(breaker)
                self._log_event('breaker_cleared', f"{breaker_type.value}")
                self._trigger_callbacks('on_breaker_cleared', breaker)

    def update_on_trade(self, pnl: float, is_win: bool) -> None:
        """
        Update state after a trade.

        Args:
            pnl: Profit/loss from trade
            is_win: Whether trade was profitable
        """
        self.state.daily_pnl += pnl
        self.state.daily_trades += 1

        if is_win:
            self.state.consecutive_losses = 0
            # Clear consecutive loss breaker on win
            self._clear_breaker(CircuitBreakerType.CONSECUTIVE_LOSSES)
        else:
            self.state.consecutive_losses += 1
            self.state.daily_losses += 1

    def update_drawdown(self, current_capital: float, peak_capital: float) -> None:
        """Update drawdown tracking."""
        if peak_capital > 0:
            self.state.total_drawdown_pct = (peak_capital - current_capital) / peak_capital

            # Check if we can resume from drawdown stop
            if self.state.total_drawdown_pct < self.config.drawdown_resume_threshold:
                self._clear_breaker(CircuitBreakerType.TOTAL_DRAWDOWN)

    def increment_bar(self) -> None:
        """Call at each new bar to update bar counters."""
        self.state.bars_since_regime_change += 1

    def manual_stop(self, reason: str) -> None:
        """Manually stop trading."""
        breaker = self._get_or_create_breaker(
            CircuitBreakerType.MANUAL_STOP,
            reason,
            'emergency'
        )
        breaker.resume_condition = "Manual resume required"
        self.state.is_trading_allowed = False
        self._log_event('manual_stop', reason)
        self._trigger_callbacks('on_trading_stopped', breaker)

    def manual_resume(self) -> None:
        """Manually resume trading."""
        self._clear_breaker(CircuitBreakerType.MANUAL_STOP)
        self._clear_breaker(CircuitBreakerType.TOTAL_DRAWDOWN)
        self.state.is_trading_allowed = True
        self._log_event('manual_resume', "Trading resumed manually")
        self._trigger_callbacks('on_trading_resumed', None)

    def register_callback(self, event: str, callback: Callable) -> None:
        """Register a callback for an event."""
        if event in self.callbacks:
            self.callbacks[event].append(callback)

    def _trigger_callbacks(self, event: str, data: Any) -> None:
        """Trigger callbacks for an event."""
        for callback in self.callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")

    def _log_event(self, event_type: str, message: str) -> None:
        """Log a safety event."""
        event = {
            'timestamp': datetime.now(),
            'type': event_type,
            'message': message
        }
        self.event_log.append(event)
        self.logger.info(f"Safety event: {event_type} - {message}")

    def get_status(self) -> Dict[str, Any]:
        """Get current safety system status."""
        return {
            'is_trading_allowed': self.state.is_trading_allowed,
            'position_multiplier': self.state.position_size_multiplier,
            'active_breakers': [
                {
                    'type': b.breaker_type.value,
                    'reason': b.reason,
                    'severity': b.severity,
                    'triggered_at': b.triggered_at.isoformat(),
                    'resume_condition': b.resume_condition
                }
                for b in self.state.active_breakers
            ],
            'consecutive_losses': self.state.consecutive_losses,
            'daily_pnl': self.state.daily_pnl,
            'daily_trades': self.state.daily_trades,
            'total_drawdown_pct': self.state.total_drawdown_pct,
            'volatility_ratio': self.state.current_volatility_ratio,
            'last_regime': self.state.last_regime.value if self.state.last_regime else None
        }

    def get_event_log(self, last_n: int = 50) -> List[Dict]:
        """Get recent events from the log."""
        return self.event_log[-last_n:]

    def reset(self) -> None:
        """Reset all state (for backtesting)."""
        self.state = SafetyState()
        self.event_log = []
