"""
Parameter Optimizer for regime-based strategy tuning.

Dynamically adjusts strategy parameters based on market regime.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/src/', 1)[0])

from src.ml.regime_detector import MarketRegime
from src.ml.strategy_selector import StrategyType


@dataclass
class RegimeParams:
    """Parameters for a specific regime."""
    position_size_pct: float
    risk_per_trade_pct: float
    stop_loss_atr_mult: float
    take_profit_atr_mult: float
    trailing_stop_enabled: bool
    trailing_stop_atr_mult: float


# Default parameters per regime
DEFAULT_REGIME_PARAMS = {
    MarketRegime.BULL: RegimeParams(
        position_size_pct=0.80,
        risk_per_trade_pct=0.03,
        stop_loss_atr_mult=2.5,
        take_profit_atr_mult=4.0,
        trailing_stop_enabled=True,
        trailing_stop_atr_mult=2.0
    ),
    MarketRegime.BEAR: RegimeParams(
        position_size_pct=0.50,
        risk_per_trade_pct=0.02,
        stop_loss_atr_mult=2.0,
        take_profit_atr_mult=3.0,
        trailing_stop_enabled=True,
        trailing_stop_atr_mult=1.5
    ),
    MarketRegime.SIDEWAYS: RegimeParams(
        position_size_pct=0.60,
        risk_per_trade_pct=0.02,
        stop_loss_atr_mult=1.5,
        take_profit_atr_mult=2.5,
        trailing_stop_enabled=False,
        trailing_stop_atr_mult=1.5
    ),
    MarketRegime.CORRECTION: RegimeParams(
        position_size_pct=0.30,
        risk_per_trade_pct=0.01,
        stop_loss_atr_mult=1.5,
        take_profit_atr_mult=2.0,
        trailing_stop_enabled=False,
        trailing_stop_atr_mult=1.0
    )
}


@dataclass
class StrategyParams:
    """Parameters for a specific strategy."""
    # Common parameters
    stop_loss_atr: float = 2.0
    take_profit_atr: float = 3.0
    trailing_stop: bool = False
    trailing_atr: float = 1.5

    # Strategy-specific
    fast_period: int = 9
    slow_period: int = 21
    trend_period: int = 50
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    bb_period: int = 20
    bb_std: float = 2.0
    supertrend_period: int = 10
    supertrend_mult: float = 3.0


# Default strategy parameters
DEFAULT_STRATEGY_PARAMS = {
    StrategyType.EMA_CROSS: StrategyParams(
        fast_period=9,
        slow_period=21,
        trend_period=50,
        stop_loss_atr=2.0,
        take_profit_atr=3.0
    ),
    StrategyType.RSI_REVERSAL: StrategyParams(
        rsi_period=14,
        rsi_oversold=30,
        rsi_overbought=70,
        bb_period=20,
        stop_loss_atr=1.5,
        take_profit_atr=2.5
    ),
    StrategyType.TREND_FOLLOW: StrategyParams(
        supertrend_period=10,
        supertrend_mult=3.0,
        trend_period=100,
        stop_loss_atr=2.5,
        take_profit_atr=4.0,
        trailing_stop=True,
        trailing_atr=2.0
    ),
    StrategyType.HULL_MA: StrategyParams(
        fast_period=16,
        slow_period=32,
        stop_loss_atr=2.0,
        take_profit_atr=3.5
    ),
    StrategyType.KELTNER_SQUEEZE: StrategyParams(
        fast_period=20,
        bb_period=20,
        bb_std=2.0,
        stop_loss_atr=1.5,
        take_profit_atr=2.5
    ),
    StrategyType.WILLIAMS_RSI: StrategyParams(
        rsi_period=14,
        rsi_oversold=20,
        rsi_overbought=80,
        stop_loss_atr=1.5,
        take_profit_atr=2.0
    ),
    StrategyType.DONCHIAN_BREAKOUT: StrategyParams(
        fast_period=20,
        slow_period=55,
        stop_loss_atr=2.0,
        take_profit_atr=3.5,
        trailing_stop=True,
        trailing_atr=1.5
    ),
    StrategyType.MOMENTUM: StrategyParams(
        fast_period=10,
        slow_period=20,
        rsi_period=14,
        stop_loss_atr=2.0,
        take_profit_atr=3.0
    )
}


class ParamOptimizer:
    """
    Dynamic parameter optimizer.

    Adjusts strategy parameters based on:
    - Current market regime
    - Recent volatility
    - Strategy type
    """

    def __init__(self):
        self.regime_params = DEFAULT_REGIME_PARAMS.copy()
        self.strategy_params = DEFAULT_STRATEGY_PARAMS.copy()
        self.optimization_history: List[Dict] = []
        self.logger = logging.getLogger(__name__)

    def get_regime_params(self, regime: MarketRegime) -> RegimeParams:
        """Get parameters for a specific regime."""
        return self.regime_params.get(regime, DEFAULT_REGIME_PARAMS[MarketRegime.SIDEWAYS])

    def get_strategy_params(self, strategy: StrategyType) -> StrategyParams:
        """Get parameters for a specific strategy."""
        return self.strategy_params.get(strategy, StrategyParams())

    def get_optimized_params(self,
                             strategy: StrategyType,
                             regime: MarketRegime,
                             current_atr_pct: float,
                             avg_atr_pct: float) -> Dict[str, Any]:
        """
        Get fully optimized parameters for current conditions.

        Args:
            strategy: Selected strategy
            regime: Current market regime
            current_atr_pct: Current ATR as % of price
            avg_atr_pct: Average ATR as % of price

        Returns:
            Dict of optimized parameters
        """
        # Get base parameters
        regime_p = self.get_regime_params(regime)
        strategy_p = self.get_strategy_params(strategy)

        # Volatility adjustment factor
        vol_ratio = current_atr_pct / avg_atr_pct if avg_atr_pct > 0 else 1.0
        vol_adjustment = self._calculate_volatility_adjustment(vol_ratio)

        # Combine and adjust parameters
        params = {
            # Position sizing from regime
            'position_size_pct': regime_p.position_size_pct * vol_adjustment['position_mult'],
            'risk_per_trade_pct': regime_p.risk_per_trade_pct * vol_adjustment['risk_mult'],

            # Stop/TP from strategy, adjusted by regime and volatility
            'stop_loss_atr': strategy_p.stop_loss_atr * regime_p.stop_loss_atr_mult / 2.0,
            'take_profit_atr': strategy_p.take_profit_atr * regime_p.take_profit_atr_mult / 3.0,

            # Trailing stop
            'trailing_stop_enabled': regime_p.trailing_stop_enabled and strategy_p.trailing_stop,
            'trailing_stop_atr': strategy_p.trailing_atr * regime_p.trailing_stop_atr_mult / 1.5,

            # Strategy-specific parameters
            'fast_period': strategy_p.fast_period,
            'slow_period': strategy_p.slow_period,
            'trend_period': strategy_p.trend_period,
            'rsi_period': strategy_p.rsi_period,
            'rsi_oversold': strategy_p.rsi_oversold,
            'rsi_overbought': strategy_p.rsi_overbought,
            'bb_period': strategy_p.bb_period,
            'bb_std': strategy_p.bb_std,
            'supertrend_period': strategy_p.supertrend_period,
            'supertrend_mult': strategy_p.supertrend_mult,

            # Context
            'regime': regime.value,
            'strategy': strategy.name,
            'volatility_ratio': vol_ratio,
            'volatility_adjustment': vol_adjustment
        }

        # Log optimization
        self.optimization_history.append({
            'strategy': strategy.name,
            'regime': regime.value,
            'vol_ratio': vol_ratio,
            'params': params.copy()
        })

        return params

    def _calculate_volatility_adjustment(self, vol_ratio: float) -> Dict[str, float]:
        """
        Calculate adjustments based on volatility.

        High volatility (>1.5x avg): Reduce position, tighten stops
        Low volatility (<0.7x avg): Normal or slightly larger positions
        """
        adjustments = {
            'position_mult': 1.0,
            'risk_mult': 1.0,
            'stop_mult': 1.0
        }

        if vol_ratio > 2.0:
            # Very high volatility - extreme caution
            adjustments['position_mult'] = 0.5
            adjustments['risk_mult'] = 0.5
            adjustments['stop_mult'] = 0.8  # Tighter stops
        elif vol_ratio > 1.5:
            # High volatility - reduce exposure
            adjustments['position_mult'] = 0.7
            adjustments['risk_mult'] = 0.75
            adjustments['stop_mult'] = 0.9
        elif vol_ratio < 0.5:
            # Very low volatility - can be more aggressive
            adjustments['position_mult'] = 1.1
            adjustments['risk_mult'] = 1.0
            adjustments['stop_mult'] = 1.1
        elif vol_ratio < 0.7:
            # Low volatility - normal
            adjustments['position_mult'] = 1.0
            adjustments['risk_mult'] = 1.0
            adjustments['stop_mult'] = 1.0

        return adjustments

    def adjust_for_performance(self,
                               strategy: StrategyType,
                               recent_win_rate: float,
                               recent_profit_factor: float) -> Dict[str, float]:
        """
        Adjust parameters based on recent performance.

        Args:
            strategy: Strategy to adjust
            recent_win_rate: Win rate over recent trades
            recent_profit_factor: Profit factor over recent trades

        Returns:
            Adjustment multipliers
        """
        adjustments = {
            'position_mult': 1.0,
            'risk_mult': 1.0
        }

        # Poor performance - reduce exposure
        if recent_win_rate < 0.3 or recent_profit_factor < 0.8:
            adjustments['position_mult'] = 0.5
            adjustments['risk_mult'] = 0.5
            self.logger.warning(
                f"Poor performance detected for {strategy.name}, reducing exposure"
            )

        # Very poor - minimal exposure
        elif recent_win_rate < 0.2 or recent_profit_factor < 0.5:
            adjustments['position_mult'] = 0.25
            adjustments['risk_mult'] = 0.25
            self.logger.warning(
                f"Very poor performance for {strategy.name}, minimal exposure"
            )

        # Good performance - can increase slightly
        elif recent_win_rate > 0.5 and recent_profit_factor > 1.5:
            adjustments['position_mult'] = 1.1
            adjustments['risk_mult'] = 1.0

        return adjustments

    def get_stop_levels(self,
                        entry_price: float,
                        atr_value: float,
                        is_long: bool,
                        strategy: StrategyType,
                        regime: MarketRegime) -> Tuple[float, float]:
        """
        Calculate stop loss and take profit levels.

        Args:
            entry_price: Entry price
            atr_value: Current ATR value
            is_long: True for long position
            strategy: Strategy type
            regime: Current regime

        Returns:
            Tuple of (stop_loss_price, take_profit_price)
        """
        regime_p = self.get_regime_params(regime)
        strategy_p = self.get_strategy_params(strategy)

        # Calculate distances
        sl_distance = atr_value * strategy_p.stop_loss_atr * (regime_p.stop_loss_atr_mult / 2.0)
        tp_distance = atr_value * strategy_p.take_profit_atr * (regime_p.take_profit_atr_mult / 3.0)

        if is_long:
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance

        return stop_loss, take_profit

    def update_regime_params(self, regime: MarketRegime, new_params: RegimeParams) -> None:
        """Update parameters for a regime."""
        self.regime_params[regime] = new_params

    def update_strategy_params(self, strategy: StrategyType, new_params: StrategyParams) -> None:
        """Update parameters for a strategy."""
        self.strategy_params[strategy] = new_params

    def get_optimization_summary(self) -> pd.DataFrame:
        """Get summary of optimization history."""
        if not self.optimization_history:
            return pd.DataFrame()

        rows = []
        for opt in self.optimization_history:
            row = {
                'strategy': opt['strategy'],
                'regime': opt['regime'],
                'vol_ratio': opt['vol_ratio'],
                'position_pct': opt['params'].get('position_size_pct', 0),
                'risk_pct': opt['params'].get('risk_per_trade_pct', 0),
                'stop_atr': opt['params'].get('stop_loss_atr', 0),
                'tp_atr': opt['params'].get('take_profit_atr', 0)
            }
            rows.append(row)

        return pd.DataFrame(rows)


def get_optimal_params(strategy: StrategyType,
                       regime: MarketRegime,
                       current_atr_pct: float = 0.02,
                       avg_atr_pct: float = 0.02) -> Dict[str, Any]:
    """
    Quick function to get optimized parameters.

    Args:
        strategy: Strategy type
        regime: Market regime
        current_atr_pct: Current ATR %
        avg_atr_pct: Average ATR %

    Returns:
        Optimized parameters dict
    """
    optimizer = ParamOptimizer()
    return optimizer.get_optimized_params(strategy, regime, current_atr_pct, avg_atr_pct)
