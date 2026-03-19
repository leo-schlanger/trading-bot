"""
Regime-Based Signal Generation (2026 Best Practices)

Based on research from:
- Academic HMM models for crypto regime detection
- Institutional trading approaches
- Freqtrade community strategies
- On-chain metrics integration

Key principles:
1. Always confirm regime first
2. Use multiple confirmations (3-4 aligned indicators)
3. Adjust position size and stops based on regime
4. Different strategies per regime
5. Both long AND short signals in all regimes
"""

import pandas as pd
import numpy as np
from enum import Enum
from typing import Dict, Tuple, Optional
from dataclasses import dataclass


class SignalDirection(Enum):
    LONG = 1
    SHORT = -1
    NEUTRAL = 0


class SignalStrength(Enum):
    STRONG = 3
    MODERATE = 2
    WEAK = 1
    NONE = 0


@dataclass
class TradeSignal:
    direction: SignalDirection
    strength: SignalStrength
    confidence: float  # 0-1
    strategy: str
    reasons: list
    stop_multiplier: float  # ATR multiplier for stop
    target_multiplier: float  # ATR multiplier for take profit
    position_size_pct: float  # Suggested position size as % of capital


class RegimeSignalGenerator:
    """
    Generates trading signals adapted to market regime.

    Regime-specific behavior:
    - BULL: Aggressive longs, defensive shorts
    - BEAR: Aggressive shorts, quick bounce longs
    - SIDEWAYS: Mean reversion, range trading
    - CORRECTION: Minimal trading, tight stops
    """

    def __init__(self):
        # Regime-specific parameters
        self.regime_config = {
            'BULL': {
                'long_bias': 0.7,      # Favor longs
                'position_size': 0.8,  # 80% of normal
                'stop_atr': 3.0,       # Wider stops
                'target_atr': 4.5,     # Larger targets
                'min_confirmations': 3,
            },
            'BEAR': {
                'long_bias': 0.3,      # Favor shorts
                'position_size': 0.5,  # 50% of normal
                'stop_atr': 2.0,       # Tighter stops
                'target_atr': 3.0,
                'min_confirmations': 3,
            },
            'SIDEWAYS': {
                'long_bias': 0.5,      # Neutral
                'position_size': 0.6,  # 60% of normal
                'stop_atr': 1.5,       # Tight stops
                'target_atr': 2.0,     # Quick targets
                'min_confirmations': 4,  # Need more confirmation
            },
            'CORRECTION': {
                'long_bias': 0.4,
                'position_size': 0.3,  # Very small
                'stop_atr': 1.5,
                'target_atr': 2.0,
                'min_confirmations': 4,
            }
        }

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all required indicators."""
        df = df.copy()

        # EMAs
        df['ema_9'] = df['close'].ewm(span=9).mean()
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        df['ema_200'] = df['close'].ewm(span=200).mean()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.inf)
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        ema_12 = df['close'].ewm(span=12).mean()
        ema_26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()

        # ADX
        df['adx'], df['plus_di'], df['minus_di'] = self._calculate_adx(df)

        # Supertrend
        df['supertrend'], df['supertrend_dir'] = self._calculate_supertrend(df)

        # Bollinger Bands
        df['bb_mid'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_mid'] + (bb_std * 2)
        df['bb_lower'] = df['bb_mid'] - (bb_std * 2)
        df['bb_pct'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # Volume analysis
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']

        # Momentum
        df['roc'] = df['close'].pct_change(10) * 100

        return df

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate ADX, +DI, -DI."""
        high = df['high']
        low = df['low']
        close = df['close']

        plus_dm = high.diff()
        minus_dm = low.diff().abs() * -1

        plus_dm = plus_dm.where((plus_dm > minus_dm.abs()) & (plus_dm > 0), 0)
        minus_dm = minus_dm.abs().where((minus_dm.abs() > plus_dm) & (minus_dm < 0), 0)

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.inf)
        adx = dx.rolling(period).mean()

        return adx, plus_di, minus_di

    def _calculate_supertrend(self, df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
        """Calculate Supertrend indicator."""
        hl2 = (df['high'] + df['low']) / 2
        atr = df['atr'] if 'atr' in df.columns else df['close'].rolling(period).std()

        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)

        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)

        supertrend.iloc[0] = upper_band.iloc[0]
        direction.iloc[0] = 1

        for i in range(1, len(df)):
            if df['close'].iloc[i] > supertrend.iloc[i-1]:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1  # Bullish
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1  # Bearish

        return supertrend, direction

    def generate_signal(self, df: pd.DataFrame, regime: str) -> TradeSignal:
        """
        Generate trading signal based on regime and indicators.

        Returns TradeSignal with direction, strength, and parameters.
        """
        df = self.calculate_indicators(df)
        config = self.regime_config.get(regime.upper(), self.regime_config['SIDEWAYS'])

        # Get latest values
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Collect signals from different strategies
        long_signals = []
        short_signals = []

        # === TREND FOLLOWING SIGNALS ===

        # EMA alignment
        if latest['ema_9'] > latest['ema_21'] > latest['ema_50']:
            long_signals.append(('ema_bullish', 1.0))
        elif latest['ema_9'] < latest['ema_21'] < latest['ema_50']:
            short_signals.append(('ema_bearish', 1.0))

        # MACD crossover
        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            long_signals.append(('macd_cross_up', 1.2))
        elif latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            short_signals.append(('macd_cross_down', 1.2))

        # MACD histogram momentum
        if latest['macd_hist'] > 0 and latest['macd_hist'] > prev['macd_hist']:
            long_signals.append(('macd_momentum_up', 0.8))
        elif latest['macd_hist'] < 0 and latest['macd_hist'] < prev['macd_hist']:
            short_signals.append(('macd_momentum_down', 0.8))

        # Supertrend
        if latest['supertrend_dir'] == 1:
            long_signals.append(('supertrend_bullish', 1.0))
        else:
            short_signals.append(('supertrend_bearish', 1.0))

        # ADX trend strength
        if latest['adx'] > 25:
            if latest['plus_di'] > latest['minus_di']:
                long_signals.append(('adx_strong_up', 0.8))
            else:
                short_signals.append(('adx_strong_down', 0.8))

        # === MOMENTUM/RSI SIGNALS ===

        # RSI momentum (not extreme)
        if 50 < latest['rsi'] < 70:
            long_signals.append(('rsi_bullish', 0.7))
        elif 30 < latest['rsi'] < 50:
            short_signals.append(('rsi_bearish', 0.7))

        # RSI extreme (mean reversion)
        if latest['rsi'] < 30:
            long_signals.append(('rsi_oversold', 1.0 if regime != 'BEAR' else 0.5))
        elif latest['rsi'] > 70:
            short_signals.append(('rsi_overbought', 1.0 if regime != 'BULL' else 0.5))

        # === VOLATILITY/BOLLINGER SIGNALS ===

        # Bollinger Band position
        if latest['bb_pct'] < 0.2:
            long_signals.append(('bb_oversold', 0.8))
        elif latest['bb_pct'] > 0.8:
            short_signals.append(('bb_overbought', 0.8))

        # === VOLUME CONFIRMATION ===

        if latest['volume_ratio'] > 1.5:
            # High volume confirms the move
            if latest['close'] > prev['close']:
                long_signals.append(('volume_confirm_up', 0.6))
            else:
                short_signals.append(('volume_confirm_down', 0.6))

        # === REGIME-SPECIFIC ADJUSTMENTS ===

        long_score = sum(weight for _, weight in long_signals)
        short_score = sum(weight for _, weight in short_signals)

        # Apply regime bias
        long_score *= config['long_bias'] + 0.3  # Base + bias
        short_score *= (1 - config['long_bias']) + 0.3

        # Determine direction
        min_confirmations = config['min_confirmations']

        if long_score > short_score and len(long_signals) >= min_confirmations:
            direction = SignalDirection.LONG
            score = long_score
            reasons = [r for r, _ in long_signals]

        elif short_score > long_score and len(short_signals) >= min_confirmations:
            direction = SignalDirection.SHORT
            score = short_score
            reasons = [r for r, _ in short_signals]

        else:
            return TradeSignal(
                direction=SignalDirection.NEUTRAL,
                strength=SignalStrength.NONE,
                confidence=0.0,
                strategy='none',
                reasons=['insufficient_confirmations'],
                stop_multiplier=0,
                target_multiplier=0,
                position_size_pct=0
            )

        # Calculate strength and confidence
        if score > 5:
            strength = SignalStrength.STRONG
        elif score > 3:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK

        confidence = min(score / 8, 1.0)  # Normalize to 0-1

        # Determine strategy name
        if 'macd_cross' in str(reasons) or 'ema' in str(reasons):
            strategy = 'trend_following'
        elif 'rsi_oversold' in reasons or 'rsi_overbought' in reasons:
            strategy = 'mean_reversion'
        elif 'bb_' in str(reasons):
            strategy = 'volatility_breakout'
        else:
            strategy = 'momentum'

        return TradeSignal(
            direction=direction,
            strength=strength,
            confidence=confidence,
            strategy=strategy,
            reasons=reasons,
            stop_multiplier=config['stop_atr'],
            target_multiplier=config['target_atr'],
            position_size_pct=config['position_size'] * (0.5 + confidence * 0.5)
        )

    def get_regime_strategy_recommendation(self, regime: str) -> Dict:
        """Get recommended strategy allocation for regime."""
        recommendations = {
            'BULL': {
                'primary': 'trend_following_long',
                'secondary': 'momentum_long',
                'avoid': 'aggressive_shorts',
                'allocation': {'long': 70, 'short': 10, 'cash': 20},
                'leverage_max': 5,
                'description': 'Aggressive longs, ride the trend with wider stops'
            },
            'BEAR': {
                'primary': 'trend_following_short',
                'secondary': 'quick_bounce_long',
                'avoid': 'holding_longs',
                'allocation': {'long': 20, 'short': 40, 'cash': 40},
                'leverage_max': 3,
                'description': 'Aggressive shorts, quick scalp bounces only'
            },
            'SIDEWAYS': {
                'primary': 'mean_reversion',
                'secondary': 'range_trading',
                'avoid': 'trend_following',
                'allocation': {'long': 35, 'short': 35, 'cash': 30},
                'leverage_max': 2,
                'description': 'Buy support, sell resistance, tight stops'
            },
            'CORRECTION': {
                'primary': 'capital_preservation',
                'secondary': 'oversold_bounces',
                'avoid': 'new_positions',
                'allocation': {'long': 10, 'short': 10, 'cash': 80},
                'leverage_max': 1,
                'description': 'Minimal trading, wait for clarity'
            }
        }
        return recommendations.get(regime.upper(), recommendations['SIDEWAYS'])
