"""
Intelligent Trading Engine.

Integrates:
- Regime detection (HMM + Rules)
- Strategy selection (XGBoost)
- Dynamic risk management
- Safety controls

Provides automated strategy switching based on market conditions.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/src/', 1)[0])

from src.backtest.engine import BacktestConfig, BaseStrategy
from src.backtest.position import Position, Trade, Side
from src.backtest.metrics import calculate_metrics
from src.indicators.technical import atr, sma
from src.ml.regime_detector import RegimeDetector, MarketRegime
from src.ml.strategy_selector import StrategySelector, StrategyType, STRATEGY_NAMES
from src.ml.features import FeatureGenerator
from src.optimization.risk_manager import RiskManager, RiskConfig
from src.optimization.param_optimizer import ParamOptimizer
from src.bot.safety_controls import SafetyControls, CircuitBreakerConfig


@dataclass
class IntelligentConfig:
    """Configuration for the intelligent engine."""
    # Capital
    initial_capital: float = 500.0

    # Fees and slippage
    maker_fee: float = 0.0002
    taker_fee: float = 0.001
    slippage: float = 0.0005

    # ML settings
    use_ml_strategy_selection: bool = True
    min_strategy_confidence: float = 0.3

    # Regime detection
    regime_lookback: int = 200  # Bars for regime detection

    # Risk management
    use_dynamic_sizing: bool = True
    base_risk_per_trade: float = 0.02

    # Safety
    enable_circuit_breakers: bool = True
    max_consecutive_losses: int = 3
    max_daily_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.20

    # Trailing stops
    use_trailing_stop: bool = True
    trailing_stop_atr_mult: float = 2.0

    # Logging
    log_level: str = 'INFO'


class IntelligentEngine:
    """
    Intelligent trading engine with ML-based decision making.

    Main features:
    - Automatic regime detection
    - Dynamic strategy selection
    - Adaptive position sizing
    - Comprehensive safety controls
    """

    def __init__(self,
                 config: Optional[IntelligentConfig] = None,
                 strategies: Optional[Dict[StrategyType, BaseStrategy]] = None):
        self.config = config or IntelligentConfig()
        self.strategies = strategies or {}

        # Initialize components
        self.regime_detector = RegimeDetector()
        self.strategy_selector = StrategySelector()
        self.feature_generator = FeatureGenerator()
        self.param_optimizer = ParamOptimizer()

        # Risk management
        risk_config = RiskConfig(
            initial_capital=self.config.initial_capital,
            base_risk_per_trade=self.config.base_risk_per_trade,
            max_daily_loss_pct=self.config.max_daily_loss_pct,
            max_total_drawdown_pct=self.config.max_drawdown_pct
        )
        self.risk_manager = RiskManager(risk_config)

        # Safety controls
        cb_config = CircuitBreakerConfig(
            initial_capital=self.config.initial_capital,
            max_consecutive_losses=self.config.max_consecutive_losses,
            max_daily_loss_pct=self.config.max_daily_loss_pct,
            max_total_drawdown_pct=self.config.max_drawdown_pct
        )
        self.safety_controls = SafetyControls(cb_config)

        # State
        self.reset()

        # Logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(getattr(logging, self.config.log_level))

    def reset(self):
        """Reset engine state."""
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
        self.equity_timestamps: List[datetime] = []
        self.position: Optional[Position] = None
        self.cash = self.config.initial_capital
        self.peak_capital = self.config.initial_capital

        self.current_regime: Optional[MarketRegime] = None
        self.current_strategy: Optional[StrategyType] = None
        self.current_params: Dict[str, Any] = {}

        self.daily_pnl = 0.0
        self.current_day = None

        # Decision log
        self.decision_log: List[Dict] = []

        # Reset sub-components
        self.risk_manager.reset_all(self.config.initial_capital)
        self.safety_controls.reset()

    def register_strategy(self, strategy_type: StrategyType, strategy: BaseStrategy):
        """Register a strategy for use."""
        self.strategies[strategy_type] = strategy
        self.logger.info(f"Registered strategy: {STRATEGY_NAMES[strategy_type]}")

    def run(self,
            data: pd.DataFrame,
            verbose: bool = False) -> Dict[str, Any]:
        """
        Run intelligent backtest.

        Args:
            data: DataFrame with OHLCV data
            verbose: Print progress

        Returns:
            Dict with metrics, trades, equity curve, and decision log
        """
        self.reset()

        # Validate data
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in data.columns for col in required_cols):
            raise ValueError(f"Data must contain columns: {required_cols}")

        # Setup all registered strategies
        for strategy_type, strategy in self.strategies.items():
            strategy.setup(data)

        # Calculate ATR for the entire dataset
        data = data.copy()
        data['atr'] = atr(data['high'], data['low'], data['close'], 14)
        data['atr_ma'] = sma(data['atr'], 20)

        total_bars = len(data)
        warmup = max(200, max(s.warmup_period for s in self.strategies.values()) if self.strategies else 200)

        for i in range(warmup, total_bars):
            timestamp = data.index[i]
            row = data.iloc[i]

            # Check for new day
            self._check_new_day(timestamp)

            # Update safety controls
            self.safety_controls.increment_bar()

            # Get current market data for analysis
            lookback_data = data.iloc[max(0, i-self.config.regime_lookback):i+1]

            # Detect regime
            regime, regime_scores = self.regime_detector.detect(lookback_data)
            self.current_regime = regime

            # Safety checks
            current_atr = row['atr'] if not pd.isna(row['atr']) else 0
            avg_atr = row['atr_ma'] if not pd.isna(row['atr_ma']) else current_atr

            safety_result = self.safety_controls.check_all(
                regime,
                current_atr,
                avg_atr
            )

            # Check if trading allowed
            can_trade, reason = self.risk_manager.can_trade(regime)
            if not can_trade or not safety_result['can_trade']:
                self._update_equity(timestamp, row['close'])
                if self.position:
                    # Check stops even if trading disabled
                    self._check_stops(row, timestamp)
                continue

            # Check stops for existing position
            if self.position:
                self._check_stops(row, timestamp)

            # If no position, look for entry
            if not self.position and self.strategies:
                entry_decision = self._make_entry_decision(
                    data, i, regime, regime_scores, safety_result
                )

                if entry_decision['should_enter']:
                    self._open_position(
                        timestamp=timestamp,
                        side=entry_decision['side'],
                        price=row['close'],
                        stop_loss=entry_decision['stop_loss'],
                        take_profit=entry_decision['take_profit'],
                        strategy=entry_decision['strategy'],
                        position_size=entry_decision['position_size']
                    )

            # If has position, check for exit
            elif self.position:
                exit_decision = self._make_exit_decision(data, i)

                if exit_decision['should_exit']:
                    self._close_position(
                        timestamp=timestamp,
                        price=row['close'],
                        reason=exit_decision['reason']
                    )

                # Update trailing stop
                elif self.config.use_trailing_stop and current_atr > 0:
                    self.position.update_trailing_stop(
                        row['close'],
                        current_atr,
                        self.current_params.get('trailing_stop_atr', self.config.trailing_stop_atr_mult)
                    )

            # Update equity
            self._update_equity(timestamp, row['close'])

            # Progress
            if verbose and i % 1000 == 0:
                pct = (i / total_bars) * 100
                print(f"Progress: {pct:.1f}% | Regime: {regime.value} | "
                      f"Strategy: {STRATEGY_NAMES.get(self.current_strategy, 'None')} | "
                      f"Capital: ${self.cash:.2f}")

        # Close any open position
        if self.position:
            self._close_position(
                timestamp=data.index[-1],
                price=data.iloc[-1]['close'],
                reason='end_of_data'
            )
            self._update_equity(data.index[-1], data.iloc[-1]['close'])

        # Calculate metrics
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
            'equity_curve': equity_series,
            'decision_log': self.decision_log,
            'regime_history': [r.value for r in self.regime_detector.regime_history],
            'safety_events': self.safety_controls.get_event_log()
        }

    def _make_entry_decision(self,
                             data: pd.DataFrame,
                             index: int,
                             regime: MarketRegime,
                             regime_scores: Dict[str, float],
                             safety_result: Dict) -> Dict[str, Any]:
        """
        Make entry decision using ML and strategy signals.

        Returns dict with:
        - should_enter: bool
        - side: Side
        - strategy: StrategyType
        - stop_loss: float
        - take_profit: float
        - position_size: float
        """
        decision = {
            'should_enter': False,
            'side': None,
            'strategy': None,
            'stop_loss': None,
            'take_profit': None,
            'position_size': 0
        }

        # Select strategy
        if self.config.use_ml_strategy_selection:
            lookback_data = data.iloc[max(0, index-200):index+1]
            strategy_type, confidence, prob_dict = self.strategy_selector.select_strategy(
                lookback_data, regime
            )
        else:
            # Default to trend follow in trending markets, RSI in sideways
            if regime in [MarketRegime.BULL, MarketRegime.BEAR]:
                strategy_type = StrategyType.TREND_FOLLOW
            else:
                strategy_type = StrategyType.RSI_REVERSAL
            confidence = 0.5

        # Check if we have this strategy registered
        if strategy_type not in self.strategies:
            # Fallback to first available
            if self.strategies:
                strategy_type = list(self.strategies.keys())[0]
            else:
                return decision

        strategy = self.strategies[strategy_type]
        self.current_strategy = strategy_type

        # Get signal from strategy
        signal = strategy.generate_signal(data, index)

        if signal == 0:
            return decision

        # Get optimized parameters
        row = data.iloc[index]
        current_atr_pct = row['atr'] / row['close'] if row['close'] > 0 else 0.02
        avg_atr_pct = row['atr_ma'] / row['close'] if row['close'] > 0 else 0.02

        self.current_params = self.param_optimizer.get_optimized_params(
            strategy_type, regime, current_atr_pct, avg_atr_pct
        )

        # Calculate position size
        stop_loss = strategy.get_stop_loss(data, index, signal)
        take_profit = strategy.get_take_profit(data, index, signal)

        if stop_loss is None:
            # Use ATR-based stop
            atr_val = row['atr']
            sl_mult = self.current_params.get('stop_loss_atr', 2.0)
            if signal > 0:
                stop_loss = row['close'] - (atr_val * sl_mult)
            else:
                stop_loss = row['close'] + (atr_val * sl_mult)

        if take_profit is None:
            # Use ATR-based TP
            atr_val = row['atr']
            tp_mult = self.current_params.get('take_profit_atr', 3.0)
            if signal > 0:
                take_profit = row['close'] + (atr_val * tp_mult)
            else:
                take_profit = row['close'] - (atr_val * tp_mult)

        # Calculate position size with risk management
        sizing = self.risk_manager.get_position_size(
            regime,
            row['close'],
            stop_loss
        )

        # Apply safety position multiplier
        position_value = sizing['position_value'] * safety_result.get('position_multiplier', 1.0)

        if position_value < 10:  # Minimum position
            return decision

        # Log decision
        self.decision_log.append({
            'timestamp': data.index[index],
            'type': 'entry_signal',
            'regime': regime.value,
            'strategy': strategy_type.name,
            'signal': signal,
            'confidence': confidence,
            'position_value': position_value
        })

        decision['should_enter'] = True
        decision['side'] = Side.LONG if signal > 0 else Side.SHORT
        decision['strategy'] = strategy_type
        decision['stop_loss'] = stop_loss
        decision['take_profit'] = take_profit
        decision['position_size'] = position_value / row['close']

        return decision

    def _make_exit_decision(self, data: pd.DataFrame, index: int) -> Dict[str, Any]:
        """
        Make exit decision based on strategy signal.

        Returns dict with:
        - should_exit: bool
        - reason: str
        """
        decision = {'should_exit': False, 'reason': None}

        if not self.position or self.current_strategy not in self.strategies:
            return decision

        strategy = self.strategies[self.current_strategy]
        signal = strategy.generate_signal(data, index)

        # Exit on opposite signal
        if self.position.side == Side.LONG and signal < 0:
            decision['should_exit'] = True
            decision['reason'] = 'signal_reversal'
        elif self.position.side == Side.SHORT and signal > 0:
            decision['should_exit'] = True
            decision['reason'] = 'signal_reversal'

        return decision

    def _open_position(self,
                       timestamp: datetime,
                       side: Side,
                       price: float,
                       stop_loss: float,
                       take_profit: float,
                       strategy: StrategyType,
                       position_size: float):
        """Open a new position."""
        if self.cash < 10:
            return

        # Apply slippage
        if side == Side.LONG:
            entry_price = price * (1 + self.config.slippage)
        else:
            entry_price = price * (1 - self.config.slippage)

        # Calculate value and fees
        position_value = min(position_size * entry_price, self.cash * 0.95)
        size = position_value / entry_price
        fee = position_value * self.config.taker_fee

        if position_value + fee > self.cash:
            position_value = self.cash - fee
            size = position_value / entry_price

        # Deduct from cash
        self.cash -= (position_value + fee)

        self.position = Position(
            entry_time=timestamp,
            side=side,
            entry_price=entry_price,
            size=size,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        self.logger.info(
            f"Opened {side.name} position: {size:.6f} @ ${entry_price:.2f} | "
            f"Strategy: {STRATEGY_NAMES[strategy]} | SL: ${stop_loss:.2f} | TP: ${take_profit:.2f}"
        )

    def _close_position(self, timestamp: datetime, price: float, reason: str):
        """Close current position."""
        if not self.position:
            return

        # Apply slippage
        if self.position.side == Side.LONG:
            exit_price = price * (1 - self.config.slippage)
        else:
            exit_price = price * (1 + self.config.slippage)

        # Calculate PnL
        pnl = self.position.calculate_pnl(exit_price)
        pnl_pct = self.position.calculate_pnl_pct(exit_price)

        # Fees
        exit_fee = exit_price * self.position.size * self.config.taker_fee
        entry_fee = self.position.entry_price * self.position.size * self.config.taker_fee
        total_fees = exit_fee + entry_fee
        pnl -= total_fees

        # Exit value
        exit_value = self.position.size * exit_price

        # Record trade
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

        # Update cash and tracking
        self.cash += exit_value - exit_fee
        self.daily_pnl += pnl

        # Update peak capital
        if self.cash > self.peak_capital:
            self.peak_capital = self.cash

        # Update risk manager and safety controls
        is_win = pnl > 0
        self.risk_manager.update_on_trade(pnl, is_win)
        self.safety_controls.update_on_trade(pnl, is_win)
        self.safety_controls.update_drawdown(self.cash, self.peak_capital)

        # Log
        self.decision_log.append({
            'timestamp': timestamp,
            'type': 'exit',
            'reason': reason,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'capital_after': self.cash
        })

        self.logger.info(
            f"Closed position: PnL=${pnl:.2f} ({pnl_pct*100:.2f}%) | "
            f"Reason: {reason} | Capital: ${self.cash:.2f}"
        )

        self.position = None

    def _check_stops(self, row: pd.Series, timestamp: datetime):
        """Check stop loss and take profit."""
        if not self.position:
            return

        if self.position.side == Side.LONG:
            if self.position.stop_loss and row['low'] <= self.position.stop_loss:
                self._close_position(timestamp, self.position.stop_loss, 'stop_loss')
                return
            if self.position.take_profit and row['high'] >= self.position.take_profit:
                self._close_position(timestamp, self.position.take_profit, 'take_profit')
                return
        else:
            if self.position.stop_loss and row['high'] >= self.position.stop_loss:
                self._close_position(timestamp, self.position.stop_loss, 'stop_loss')
                return
            if self.position.take_profit and row['low'] <= self.position.take_profit:
                self._close_position(timestamp, self.position.take_profit, 'take_profit')
                return

    def _check_new_day(self, timestamp: datetime):
        """Check for day change and reset daily counters."""
        current_date = timestamp.date() if hasattr(timestamp, 'date') else None
        if current_date and current_date != self.current_day:
            self.current_day = current_date
            self.daily_pnl = 0.0
            self.risk_manager.reset_daily()

    def _update_equity(self, timestamp: datetime, current_price: float):
        """Update equity curve."""
        if self.position:
            position_value = self.position.size * current_price
            equity = self.cash + position_value
        else:
            equity = self.cash

        # Sanity bounds
        equity = max(0, min(equity, self.config.initial_capital * 1000))

        self.equity_curve.append(equity)
        self.equity_timestamps.append(timestamp)

    def get_status(self) -> Dict[str, Any]:
        """Get current engine status."""
        # Calculate current price from equity if position exists
        current_price = None
        position_pnl = None
        if self.position and self.equity_curve:
            # Current equity = cash + position_value
            # position_value = size * current_price
            # So: current_price = (equity - cash) / size
            current_equity = self.equity_curve[-1]
            if self.position.size > 0:
                current_price = (current_equity - self.cash) / self.position.size
                position_pnl = self.position.calculate_pnl(current_price)

        return {
            'cash': self.cash,
            'peak_capital': self.peak_capital,
            'position': {
                'side': self.position.side.name if self.position else None,
                'entry_price': self.position.entry_price if self.position else None,
                'size': self.position.size if self.position else None,
                'current_price': current_price,
                'pnl': position_pnl
            } if self.position else None,
            'current_regime': self.current_regime.value if self.current_regime else None,
            'current_strategy': STRATEGY_NAMES.get(self.current_strategy) if self.current_strategy else None,
            'total_trades': len(self.trades),
            'risk_metrics': self.risk_manager.get_risk_metrics(),
            'safety_status': self.safety_controls.get_status()
        }

    def load_models(self, regime_model_path: str, strategy_model_path: str):
        """Load trained ML models."""
        self.regime_detector.load_model(regime_model_path)
        self.strategy_selector.load_model(strategy_model_path)
        self.logger.info("ML models loaded successfully")

    def save_decision_log(self, path: str):
        """Save decision log to file."""
        df = pd.DataFrame(self.decision_log)
        df.to_csv(path, index=False)
        self.logger.info(f"Decision log saved to {path}")
