"""
Feature engineering for ML models.
Generates technical and statistical features for regime detection and strategy selection.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/src/', 1)[0])

from src.indicators.technical import (
    sma, ema, rsi, macd, bollinger_bands, atr,
    adx, roc, supertrend, fisher_transform
)


def safe_divide(numerator: pd.Series, denominator: pd.Series, fill_value: float = 0.0) -> pd.Series:
    """Safely divide two series, replacing inf/nan with fill_value."""
    with np.errstate(divide='ignore', invalid='ignore'):
        result = numerator / denominator
        result = result.replace([np.inf, -np.inf], fill_value)
        result = result.fillna(fill_value)
    return result


@dataclass
class FeatureConfig:
    """Configuration for feature generation."""
    ma_periods: List[int] = None
    rsi_period: int = 14
    atr_period: int = 14
    adx_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    lookback_periods: List[int] = None

    def __post_init__(self):
        if self.ma_periods is None:
            self.ma_periods = [20, 50, 100, 200]
        if self.lookback_periods is None:
            self.lookback_periods = [5, 10, 20]


class FeatureGenerator:
    """
    Generates features for ML models.

    Features include:
    - Price position relative to MAs
    - Trend strength (ADX)
    - Volatility (ATR%)
    - Momentum (ROC, RSI)
    - Drawdown from ATH
    - Volume features
    - Lagged features
    """

    def __init__(self, config: Optional[FeatureConfig] = None):
        self.config = config or FeatureConfig()
        self.feature_names: List[str] = []

    def generate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all features from OHLCV data.

        Args:
            df: DataFrame with columns [open, high, low, close, volume]

        Returns:
            DataFrame with all features
        """
        features = pd.DataFrame(index=df.index)

        # Price features
        features = self._add_price_features(df, features)

        # Trend features
        features = self._add_trend_features(df, features)

        # Momentum features
        features = self._add_momentum_features(df, features)

        # Volatility features
        features = self._add_volatility_features(df, features)

        # Volume features
        if 'volume' in df.columns:
            features = self._add_volume_features(df, features)

        # Lagged features
        features = self._add_lagged_features(features)

        # Drawdown features
        features = self._add_drawdown_features(df, features)

        self.feature_names = features.columns.tolist()

        return features

    def _add_price_features(self, df: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
        """Add price-related features."""
        close = df['close']

        # Price position relative to moving averages
        for period in self.config.ma_periods:
            ma = sma(close, period)
            features[f'price_vs_ma{period}'] = (close - ma) / ma
            features[f'price_above_ma{period}'] = (close > ma).astype(int)

        # Price momentum (simple returns)
        features['return_1'] = close.pct_change()
        features['return_5'] = close.pct_change(5)
        features['return_10'] = close.pct_change(10)
        features['return_20'] = close.pct_change(20)

        # Log returns (better for ML)
        features['log_return_1'] = np.log(close / close.shift(1))
        features['log_return_5'] = np.log(close / close.shift(5))

        # Price range features
        features['daily_range'] = (df['high'] - df['low']) / close
        features['body_size'] = abs(close - df['open']) / close
        features['upper_shadow'] = (df['high'] - np.maximum(close, df['open'])) / close
        features['lower_shadow'] = (np.minimum(close, df['open']) - df['low']) / close

        return features

    def _add_trend_features(self, df: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
        """Add trend-related features."""
        close = df['close']
        high = df['high']
        low = df['low']

        # ADX - trend strength
        adx_line, plus_di, minus_di = adx(high, low, close, self.config.adx_period)
        features['adx'] = adx_line
        features['plus_di'] = plus_di
        features['minus_di'] = minus_di
        features['di_diff'] = plus_di - minus_di

        # ADX derived features
        features['adx_trending'] = (adx_line > 25).astype(int)
        features['adx_strong_trend'] = (adx_line > 40).astype(int)

        # Supertrend
        st_line, st_direction = supertrend(high, low, close)
        features['supertrend_direction'] = st_direction
        features['price_vs_supertrend'] = (close - st_line) / st_line

        # MACD
        macd_line, signal_line, histogram = macd(
            close,
            self.config.macd_fast,
            self.config.macd_slow,
            self.config.macd_signal
        )
        features['macd'] = macd_line
        features['macd_signal'] = signal_line
        features['macd_histogram'] = histogram
        features['macd_above_signal'] = (macd_line > signal_line).astype(int)
        features['macd_positive'] = (macd_line > 0).astype(int)

        # EMA stack (trend alignment)
        ema_20 = ema(close, 20)
        ema_50 = ema(close, 50)
        ema_100 = ema(close, 100)

        features['ema_stack_bullish'] = (
            (close > ema_20) & (ema_20 > ema_50) & (ema_50 > ema_100)
        ).astype(int)
        features['ema_stack_bearish'] = (
            (close < ema_20) & (ema_20 < ema_50) & (ema_50 < ema_100)
        ).astype(int)

        return features

    def _add_momentum_features(self, df: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
        """Add momentum-related features."""
        close = df['close']
        high = df['high']
        low = df['low']

        # RSI
        rsi_val = rsi(close, self.config.rsi_period)
        features['rsi'] = rsi_val
        features['rsi_oversold'] = (rsi_val < 30).astype(int)
        features['rsi_overbought'] = (rsi_val > 70).astype(int)
        features['rsi_neutral'] = ((rsi_val >= 40) & (rsi_val <= 60)).astype(int)

        # Rate of Change
        features['roc_5'] = roc(close, 5)
        features['roc_10'] = roc(close, 10)
        features['roc_20'] = roc(close, 20)

        # Fisher Transform
        fisher_line, fisher_trigger = fisher_transform(high, low)
        features['fisher'] = fisher_line
        features['fisher_trigger'] = fisher_trigger
        features['fisher_cross'] = (fisher_line > fisher_trigger).astype(int)

        # Momentum (simple)
        features['momentum_5'] = close - close.shift(5)
        features['momentum_10'] = close - close.shift(10)
        features['momentum_20'] = close - close.shift(20)

        # Acceleration (momentum of momentum)
        features['acceleration'] = features['momentum_5'] - features['momentum_5'].shift(5)

        return features

    def _add_volatility_features(self, df: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
        """Add volatility-related features."""
        close = df['close']
        high = df['high']
        low = df['low']

        # ATR and ATR%
        atr_val = atr(high, low, close, self.config.atr_period)
        features['atr'] = atr_val
        features['atr_pct'] = atr_val / close  # Normalized ATR

        # ATR vs its moving average (volatility regime)
        atr_ma = sma(atr_val, 20)
        features['atr_vs_ma'] = safe_divide(atr_val, atr_ma, fill_value=1.0)
        features['high_volatility'] = (features['atr_vs_ma'] > 1.5).astype(int)
        features['low_volatility'] = (features['atr_vs_ma'] < 0.7).astype(int)

        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = bollinger_bands(
            close, self.config.bb_period, self.config.bb_std
        )
        bb_width = (bb_upper - bb_lower) / bb_middle
        features['bb_width'] = bb_width
        features['bb_position'] = safe_divide(close - bb_lower, bb_upper - bb_lower, fill_value=0.5)
        features['bb_squeeze'] = (bb_width < bb_width.rolling(50).mean()).astype(int)

        # Historical volatility
        features['volatility_5'] = close.pct_change().rolling(5).std() * np.sqrt(252)
        features['volatility_20'] = close.pct_change().rolling(20).std() * np.sqrt(252)

        # Parkinson volatility (uses high-low)
        hl_ratio = np.log(high / low)
        features['parkinson_vol'] = hl_ratio.rolling(20).apply(
            lambda x: np.sqrt(np.sum(x**2) / (4 * len(x) * np.log(2)))
        )

        return features

    def _add_volume_features(self, df: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
        """Add volume-related features."""
        volume = df['volume']
        close = df['close']

        # Volume vs average
        vol_ma = sma(volume, 20)
        features['volume_vs_ma'] = safe_divide(volume, vol_ma, fill_value=1.0)
        features['high_volume'] = (features['volume_vs_ma'] > 1.5).astype(int)

        # Volume trend
        features['volume_trend'] = safe_divide(sma(volume, 5), sma(volume, 20), fill_value=1.0)

        # On-Balance Volume derivative
        obv_direction = np.sign(close.diff())
        obv = (obv_direction * volume).cumsum()
        features['obv_slope'] = obv.diff(5) / 5

        # Price-Volume correlation
        features['pv_correlation'] = close.rolling(20).corr(volume)

        return features

    def _add_lagged_features(self, features: pd.DataFrame) -> pd.DataFrame:
        """Add lagged versions of key features."""
        lag_features = ['rsi', 'adx', 'atr_pct', 'return_1', 'volume_vs_ma']

        for feature in lag_features:
            if feature in features.columns:
                for lag in self.config.lookback_periods:
                    features[f'{feature}_lag{lag}'] = features[feature].shift(lag)

        return features

    def _add_drawdown_features(self, df: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
        """Add drawdown-related features."""
        close = df['close']

        # Rolling ATH and drawdown
        rolling_max = close.expanding().max()
        features['drawdown'] = (close - rolling_max) / rolling_max
        features['drawdown_pct'] = features['drawdown'] * 100

        # Is in drawdown
        features['in_drawdown'] = (features['drawdown'] < -0.05).astype(int)
        features['deep_drawdown'] = (features['drawdown'] < -0.20).astype(int)

        # Recovery from recent low
        rolling_min_20 = close.rolling(20).min()
        features['recovery_from_low'] = safe_divide(close - rolling_min_20, rolling_min_20, fill_value=0.0)

        # Distance from 20-period high
        rolling_max_20 = close.rolling(20).max()
        features['distance_from_high'] = safe_divide(close - rolling_max_20, rolling_max_20, fill_value=0.0)

        return features

    def get_feature_names(self) -> List[str]:
        """Return list of feature names."""
        return self.feature_names

    def prepare_for_ml(self,
                       features: pd.DataFrame,
                       dropna: bool = True) -> Tuple[np.ndarray, pd.Index]:
        """
        Prepare features for ML model.

        Args:
            features: DataFrame of features
            dropna: Whether to drop rows with NaN

        Returns:
            Tuple of (feature_array, valid_index)
        """
        if dropna:
            valid_mask = ~features.isna().any(axis=1)
            clean_features = features[valid_mask]
            return clean_features.values, clean_features.index

        # Fill NaN with 0 if not dropping
        return features.fillna(0).values, features.index

    def get_regime_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Get features specifically for regime detection.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with regime-specific features
        """
        features = pd.DataFrame(index=df.index)
        close = df['close']
        high = df['high']
        low = df['low']

        # MA200 position (key for bull/bear)
        ma200 = sma(close, 200)
        features['price_vs_ma200'] = (close - ma200) / ma200
        features['above_ma200'] = (close > ma200).astype(int)

        # ADX (trend strength)
        adx_line, plus_di, minus_di = adx(high, low, close, 14)
        features['adx'] = adx_line
        features['di_diff'] = plus_di - minus_di

        # Momentum
        features['roc_20'] = roc(close, 20)

        # Volatility
        atr_val = atr(high, low, close, 14)
        features['atr_pct'] = atr_val / close

        # Drawdown
        rolling_max = close.expanding().max()
        features['drawdown'] = (close - rolling_max) / rolling_max

        return features

    def get_strategy_features(self,
                              df: pd.DataFrame,
                              lookback: int = 20) -> pd.DataFrame:
        """
        Get features for strategy selection.
        Includes rolling window of recent data.

        Args:
            df: DataFrame with OHLCV data
            lookback: Number of bars to include

        Returns:
            DataFrame with strategy selection features
        """
        # Generate all features
        all_features = self.generate_features(df)

        # Select most relevant for strategy selection
        key_features = [
            'price_vs_ma200', 'adx', 'rsi', 'atr_pct',
            'macd_histogram', 'bb_position', 'roc_10',
            'supertrend_direction', 'ema_stack_bullish', 'ema_stack_bearish',
            'volatility_20', 'drawdown'
        ]

        # Filter to existing features
        existing = [f for f in key_features if f in all_features.columns]
        features = all_features[existing].copy()

        # Add rolling statistics of key metrics
        for col in ['rsi', 'adx', 'atr_pct']:
            if col in features.columns:
                features[f'{col}_mean_{lookback}'] = features[col].rolling(lookback).mean()
                features[f'{col}_std_{lookback}'] = features[col].rolling(lookback).std()

        return features
