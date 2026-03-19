"""
Adaptive Trap Detector (2026)

Detects market traps and fake signals:
- Bull traps (false breakouts up)
- Bear traps (false breakdowns)
- Fake breakouts (low volume)
- Divergences (price vs momentum)
- Exhaustion patterns

Adapts to current market conditions using volatility-adjusted parameters.
"""

import pandas as pd
import numpy as np
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


class TrapType(Enum):
    """Types of market traps."""
    BULL_TRAP = "bull_trap"
    BEAR_TRAP = "bear_trap"
    FAKE_BREAKOUT_UP = "fake_breakout_up"
    FAKE_BREAKOUT_DOWN = "fake_breakout_down"
    BULLISH_DIVERGENCE = "bullish_divergence"
    BEARISH_DIVERGENCE = "bearish_divergence"
    EXHAUSTION_TOP = "exhaustion_top"
    EXHAUSTION_BOTTOM = "exhaustion_bottom"
    VOLUME_DRY_UP = "volume_dry_up"
    STOP_HUNT = "stop_hunt"


@dataclass
class TrapSignal:
    """Detected trap signal."""
    trap_type: TrapType
    confidence: float  # 0-1
    description: str
    action_suggestion: str  # 'avoid_long', 'avoid_short', 'wait', 'reversal_long', 'reversal_short'
    invalidation_price: Optional[float] = None


@dataclass
class MarketContext:
    """Current market context for adaptive parameters."""
    volatility_ratio: float  # Current ATR / Average ATR
    trend_strength: float  # ADX value
    volume_ratio: float  # Current volume / Average volume
    regime: str  # bull, bear, sideways, correction


class TrapDetector:
    """
    Adaptive trap detection system.

    Detects market manipulation patterns and false signals
    by analyzing price action, volume, and momentum divergences.
    """

    def __init__(self):
        # Base parameters (will be adjusted by volatility)
        self.base_config = {
            'divergence_lookback': 14,
            'breakout_confirmation_bars': 2,
            'volume_threshold': 1.5,  # Volume must be 1.5x average for real breakout
            'exhaustion_volume_mult': 2.5,  # Exhaustion needs 2.5x volume
            'trap_confirmation_bars': 3,
            'stop_hunt_wick_ratio': 0.7,  # Wick must be 70% of candle for stop hunt
        }

    def detect_all_traps(self, df: pd.DataFrame, context: MarketContext) -> List[TrapSignal]:
        """
        Run all trap detection algorithms.

        Args:
            df: DataFrame with OHLCV + indicators
            context: Current market context

        Returns:
            List of detected traps
        """
        df = self._prepare_data(df)
        traps = []

        # Adjust parameters based on volatility
        params = self._adjust_parameters(context)

        # Run all detectors
        traps.extend(self._detect_bull_trap(df, params, context))
        traps.extend(self._detect_bear_trap(df, params, context))
        traps.extend(self._detect_fake_breakout(df, params, context))
        traps.extend(self._detect_divergences(df, params))
        traps.extend(self._detect_exhaustion(df, params))
        traps.extend(self._detect_stop_hunt(df, params))
        traps.extend(self._detect_volume_anomalies(df, params))

        # Sort by confidence
        traps.sort(key=lambda x: x.confidence, reverse=True)

        return traps

    def _prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate required indicators if not present."""
        df = df.copy()

        # RSI
        if 'rsi' not in df.columns:
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.inf)
            df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        if 'macd' not in df.columns:
            ema12 = df['close'].ewm(span=12).mean()
            ema26 = df['close'].ewm(span=26).mean()
            df['macd'] = ema12 - ema26
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']

        # ATR
        if 'atr' not in df.columns:
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift())
            low_close = abs(df['low'] - df['close'].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['atr'] = tr.rolling(14).mean()

        # Volume SMA
        if 'volume_sma' not in df.columns:
            df['volume_sma'] = df['volume'].rolling(20).mean()

        # Bollinger Bands
        if 'bb_upper' not in df.columns:
            df['bb_mid'] = df['close'].rolling(20).mean()
            bb_std = df['close'].rolling(20).std()
            df['bb_upper'] = df['bb_mid'] + (bb_std * 2)
            df['bb_lower'] = df['bb_mid'] - (bb_std * 2)

        # Support/Resistance levels (simplified)
        df['recent_high'] = df['high'].rolling(20).max()
        df['recent_low'] = df['low'].rolling(20).min()

        # Candle analysis
        df['body'] = abs(df['close'] - df['open'])
        df['upper_wick'] = df['high'] - df[['close', 'open']].max(axis=1)
        df['lower_wick'] = df[['close', 'open']].min(axis=1) - df['low']
        df['candle_range'] = df['high'] - df['low']

        return df

    def _adjust_parameters(self, context: MarketContext) -> Dict:
        """Adjust parameters based on current market conditions."""
        params = self.base_config.copy()

        # High volatility = need more confirmation
        if context.volatility_ratio > 1.5:
            params['breakout_confirmation_bars'] = 3
            params['volume_threshold'] = 2.0
            params['trap_confirmation_bars'] = 4
        elif context.volatility_ratio < 0.7:
            params['breakout_confirmation_bars'] = 1
            params['volume_threshold'] = 1.3
            params['trap_confirmation_bars'] = 2

        # Low trend strength = more traps likely
        if context.trend_strength < 20:
            params['volume_threshold'] *= 1.2  # Need even more volume confirmation

        return params

    def _detect_bull_trap(self, df: pd.DataFrame, params: Dict, context: MarketContext) -> List[TrapSignal]:
        """
        Detect bull traps (false breakouts above resistance).

        Pattern:
        1. Price breaks above recent high/resistance
        2. But closes back below within N bars
        3. Volume was not convincing
        """
        traps = []
        lookback = params['trap_confirmation_bars']

        if len(df) < lookback + 5:
            return traps

        latest = df.iloc[-1]
        prev_bars = df.iloc[-(lookback+1):-1]

        # Check if we had a breakout above recent high
        recent_high = df['recent_high'].iloc[-(lookback+5)]

        # Did price break above and come back?
        broke_above = prev_bars['high'].max() > recent_high
        now_below = latest['close'] < recent_high

        if broke_above and now_below:
            # Check volume - was breakout on low volume?
            breakout_bar_idx = prev_bars['high'].idxmax()
            if breakout_bar_idx in df.index:
                breakout_volume = df.loc[breakout_bar_idx, 'volume']
                avg_volume = df['volume_sma'].loc[breakout_bar_idx]

                low_volume_breakout = breakout_volume < avg_volume * params['volume_threshold']

                if low_volume_breakout:
                    confidence = 0.8
                else:
                    confidence = 0.5

                # Higher confidence in bear market (more likely to be trap)
                if context.regime == 'bear':
                    confidence += 0.1

                traps.append(TrapSignal(
                    trap_type=TrapType.BULL_TRAP,
                    confidence=min(confidence, 1.0),
                    description=f"Price broke above {recent_high:.2f} but failed to hold",
                    action_suggestion='avoid_long',
                    invalidation_price=prev_bars['high'].max()
                ))

        return traps

    def _detect_bear_trap(self, df: pd.DataFrame, params: Dict, context: MarketContext) -> List[TrapSignal]:
        """
        Detect bear traps (false breakdowns below support).

        Pattern:
        1. Price breaks below recent low/support
        2. But closes back above within N bars
        3. Volume was not convincing
        """
        traps = []
        lookback = params['trap_confirmation_bars']

        if len(df) < lookback + 5:
            return traps

        latest = df.iloc[-1]
        prev_bars = df.iloc[-(lookback+1):-1]

        # Check if we had a breakdown below recent low
        recent_low = df['recent_low'].iloc[-(lookback+5)]

        # Did price break below and come back?
        broke_below = prev_bars['low'].min() < recent_low
        now_above = latest['close'] > recent_low

        if broke_below and now_above:
            # Check volume
            breakdown_bar_idx = prev_bars['low'].idxmin()
            if breakdown_bar_idx in df.index:
                breakdown_volume = df.loc[breakdown_bar_idx, 'volume']
                avg_volume = df['volume_sma'].loc[breakdown_bar_idx]

                low_volume_breakdown = breakdown_volume < avg_volume * params['volume_threshold']

                if low_volume_breakdown:
                    confidence = 0.8
                else:
                    confidence = 0.5

                # Higher confidence in bull market
                if context.regime == 'bull':
                    confidence += 0.1

                traps.append(TrapSignal(
                    trap_type=TrapType.BEAR_TRAP,
                    confidence=min(confidence, 1.0),
                    description=f"Price broke below {recent_low:.2f} but recovered",
                    action_suggestion='avoid_short',
                    invalidation_price=prev_bars['low'].min()
                ))

        return traps

    def _detect_fake_breakout(self, df: pd.DataFrame, params: Dict, context: MarketContext) -> List[TrapSignal]:
        """
        Detect fake breakouts (Bollinger Band pierces without follow-through).
        """
        traps = []

        if len(df) < 5:
            return traps

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Fake breakout UP: pierced upper BB but closed inside
        if prev['high'] > prev['bb_upper'] and latest['close'] < latest['bb_upper']:
            # Check volume
            volume_weak = latest['volume'] < latest['volume_sma']
            confidence = 0.7 if volume_weak else 0.5

            traps.append(TrapSignal(
                trap_type=TrapType.FAKE_BREAKOUT_UP,
                confidence=confidence,
                description="Price pierced upper Bollinger Band but failed to hold",
                action_suggestion='avoid_long'
            ))

        # Fake breakout DOWN: pierced lower BB but closed inside
        if prev['low'] < prev['bb_lower'] and latest['close'] > latest['bb_lower']:
            volume_weak = latest['volume'] < latest['volume_sma']
            confidence = 0.7 if volume_weak else 0.5

            traps.append(TrapSignal(
                trap_type=TrapType.FAKE_BREAKOUT_DOWN,
                confidence=confidence,
                description="Price pierced lower Bollinger Band but recovered",
                action_suggestion='avoid_short'
            ))

        return traps

    def _detect_divergences(self, df: pd.DataFrame, params: Dict) -> List[TrapSignal]:
        """
        Detect price-momentum divergences.

        Bullish divergence: Price makes lower low, RSI makes higher low
        Bearish divergence: Price makes higher high, RSI makes lower high
        """
        traps = []
        lookback = params['divergence_lookback']

        if len(df) < lookback + 5:
            return traps

        recent = df.iloc[-lookback:]

        # Find local highs and lows
        price_highs = []
        price_lows = []
        rsi_at_highs = []
        rsi_at_lows = []

        for i in range(2, len(recent) - 2):
            # Local high
            if recent['high'].iloc[i] > recent['high'].iloc[i-1] and \
               recent['high'].iloc[i] > recent['high'].iloc[i-2] and \
               recent['high'].iloc[i] > recent['high'].iloc[i+1] and \
               recent['high'].iloc[i] > recent['high'].iloc[i+2]:
                price_highs.append(recent['high'].iloc[i])
                rsi_at_highs.append(recent['rsi'].iloc[i])

            # Local low
            if recent['low'].iloc[i] < recent['low'].iloc[i-1] and \
               recent['low'].iloc[i] < recent['low'].iloc[i-2] and \
               recent['low'].iloc[i] < recent['low'].iloc[i+1] and \
               recent['low'].iloc[i] < recent['low'].iloc[i+2]:
                price_lows.append(recent['low'].iloc[i])
                rsi_at_lows.append(recent['rsi'].iloc[i])

        # Check for bearish divergence (price higher high, RSI lower high)
        if len(price_highs) >= 2 and len(rsi_at_highs) >= 2:
            if price_highs[-1] > price_highs[-2] and rsi_at_highs[-1] < rsi_at_highs[-2]:
                confidence = 0.75
                traps.append(TrapSignal(
                    trap_type=TrapType.BEARISH_DIVERGENCE,
                    confidence=confidence,
                    description="Price making higher highs but RSI making lower highs - weakness",
                    action_suggestion='avoid_long'
                ))

        # Check for bullish divergence (price lower low, RSI higher low)
        if len(price_lows) >= 2 and len(rsi_at_lows) >= 2:
            if price_lows[-1] < price_lows[-2] and rsi_at_lows[-1] > rsi_at_lows[-2]:
                confidence = 0.75
                traps.append(TrapSignal(
                    trap_type=TrapType.BULLISH_DIVERGENCE,
                    confidence=confidence,
                    description="Price making lower lows but RSI making higher lows - strength building",
                    action_suggestion='avoid_short'
                ))

        return traps

    def _detect_exhaustion(self, df: pd.DataFrame, params: Dict) -> List[TrapSignal]:
        """
        Detect exhaustion candles (climax volume with reversal).

        Signs of exhaustion:
        1. Extremely high volume (2.5x+ average)
        2. Long wick in direction of trend
        3. Close near opposite end of candle
        """
        traps = []

        if len(df) < 5:
            return traps

        latest = df.iloc[-1]

        # Check for high volume
        volume_ratio = latest['volume'] / latest['volume_sma'] if latest['volume_sma'] > 0 else 1

        if volume_ratio < params['exhaustion_volume_mult']:
            return traps

        # Exhaustion top: high volume, long upper wick, close near low
        candle_range = latest['candle_range']
        if candle_range > 0:
            upper_wick_ratio = latest['upper_wick'] / candle_range
            lower_wick_ratio = latest['lower_wick'] / candle_range

            # Exhaustion top
            if upper_wick_ratio > 0.6 and latest['close'] < latest['open']:
                traps.append(TrapSignal(
                    trap_type=TrapType.EXHAUSTION_TOP,
                    confidence=min(0.6 + (volume_ratio - 2) * 0.1, 0.9),
                    description=f"Exhaustion candle at top with {volume_ratio:.1f}x volume",
                    action_suggestion='avoid_long'
                ))

            # Exhaustion bottom
            if lower_wick_ratio > 0.6 and latest['close'] > latest['open']:
                traps.append(TrapSignal(
                    trap_type=TrapType.EXHAUSTION_BOTTOM,
                    confidence=min(0.6 + (volume_ratio - 2) * 0.1, 0.9),
                    description=f"Exhaustion candle at bottom with {volume_ratio:.1f}x volume",
                    action_suggestion='avoid_short'
                ))

        return traps

    def _detect_stop_hunt(self, df: pd.DataFrame, params: Dict) -> List[TrapSignal]:
        """
        Detect stop hunts (quick wick beyond S/R then reversal).

        Pattern:
        1. Quick spike beyond obvious S/R level
        2. Immediate reversal
        3. Long wick relative to body
        """
        traps = []

        if len(df) < 3:
            return traps

        latest = df.iloc[-1]
        candle_range = latest['candle_range']

        if candle_range == 0:
            return traps

        wick_ratio = params['stop_hunt_wick_ratio']

        # Stop hunt above (long upper wick, bearish close)
        if latest['upper_wick'] / candle_range > wick_ratio:
            if latest['close'] < latest['open']:  # Bearish candle
                # Check if it spiked above recent high
                recent_high = df['high'].iloc[-20:-1].max()
                if latest['high'] > recent_high and latest['close'] < recent_high:
                    traps.append(TrapSignal(
                        trap_type=TrapType.STOP_HUNT,
                        confidence=0.7,
                        description="Possible stop hunt above recent highs",
                        action_suggestion='avoid_long',
                        invalidation_price=latest['high']
                    ))

        # Stop hunt below (long lower wick, bullish close)
        if latest['lower_wick'] / candle_range > wick_ratio:
            if latest['close'] > latest['open']:  # Bullish candle
                # Check if it spiked below recent low
                recent_low = df['low'].iloc[-20:-1].min()
                if latest['low'] < recent_low and latest['close'] > recent_low:
                    traps.append(TrapSignal(
                        trap_type=TrapType.STOP_HUNT,
                        confidence=0.7,
                        description="Possible stop hunt below recent lows",
                        action_suggestion='avoid_short',
                        invalidation_price=latest['low']
                    ))

        return traps

    def _detect_volume_anomalies(self, df: pd.DataFrame, params: Dict) -> List[TrapSignal]:
        """
        Detect volume anomalies that suggest manipulation.
        """
        traps = []

        if len(df) < 5:
            return traps

        latest = df.iloc[-1]
        recent_volume = df['volume'].iloc[-5:]

        # Volume dry up in a move (suspicious)
        avg_recent_volume = recent_volume.mean()
        avg_volume = df['volume_sma'].iloc[-1]

        if avg_volume > 0:
            # Price moving but volume dying
            price_move = abs(df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5]
            volume_ratio = avg_recent_volume / avg_volume

            if price_move > 0.03 and volume_ratio < 0.5:  # 3%+ move on 50% less volume
                traps.append(TrapSignal(
                    trap_type=TrapType.VOLUME_DRY_UP,
                    confidence=0.6,
                    description=f"Price moved {price_move*100:.1f}% but volume is {volume_ratio*100:.0f}% of average",
                    action_suggestion='wait'
                ))

        return traps

    def get_trap_summary(self, traps: List[TrapSignal]) -> Dict:
        """
        Summarize detected traps into actionable guidance.
        """
        if not traps:
            return {
                'has_traps': False,
                'avoid_long': False,
                'avoid_short': False,
                'wait': False,
                'highest_confidence_trap': None,
                'trap_count': 0
            }

        avoid_long = any(t.action_suggestion == 'avoid_long' for t in traps)
        avoid_short = any(t.action_suggestion == 'avoid_short' for t in traps)
        should_wait = any(t.action_suggestion == 'wait' for t in traps)

        highest = max(traps, key=lambda x: x.confidence)

        return {
            'has_traps': True,
            'avoid_long': avoid_long,
            'avoid_short': avoid_short,
            'wait': should_wait,
            'highest_confidence_trap': highest.trap_type.value,
            'trap_count': len(traps),
            'trap_details': [
                {
                    'type': t.trap_type.value,
                    'confidence': t.confidence,
                    'description': t.description,
                    'action': t.action_suggestion
                }
                for t in traps[:5]  # Top 5 traps
            ]
        }
