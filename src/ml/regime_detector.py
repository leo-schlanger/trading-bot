"""
Market Regime Detection using hybrid HMM + Rules approach.

Detects 4 market states:
- BULL: Uptrend with strong momentum
- BEAR: Downtrend with strong momentum
- SIDEWAYS: Low trend strength, ranging market
- CORRECTION: Sharp decline within a bull market
"""

import numpy as np
import pandas as pd
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

try:
    from hmmlearn.hmm import GaussianHMM
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False
    logging.warning("hmmlearn not installed. Using rule-based regime detection only.")

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/src/', 1)[0])

from src.indicators.technical import sma, ema, atr, adx, roc
from src.ml.features import FeatureGenerator


class MarketRegime(Enum):
    """Market regime states."""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    CORRECTION = "correction"


@dataclass
class RegimeConfig:
    """Configuration for regime detection."""
    # MA periods
    ma_fast: int = 50
    ma_slow: int = 200

    # ADX thresholds
    adx_trend_threshold: float = 25.0  # Above = trending
    adx_sideways_threshold: float = 20.0  # Below = sideways

    # Momentum thresholds
    momentum_period: int = 20
    momentum_bull_threshold: float = 5.0  # ROC% for bull
    momentum_bear_threshold: float = -5.0  # ROC% for bear

    # Correction detection
    correction_threshold: float = -10.0  # % drop to trigger correction
    correction_lookback: int = 5  # Bars to check for drop

    # HMM settings
    hmm_n_states: int = 4
    hmm_n_iter: int = 100
    hmm_covariance_type: str = "diag"

    # Hybrid weighting
    rule_weight: float = 0.6
    hmm_weight: float = 0.4


class RegimeDetector:
    """
    Hybrid regime detector combining rules and HMM.

    Uses:
    1. Rule-based detection for interpretable classification
    2. HMM for probabilistic state estimation
    3. Weighted combination for final decision
    """

    def __init__(self, config: Optional[RegimeConfig] = None):
        self.config = config or RegimeConfig()
        self.feature_generator = FeatureGenerator()
        self.hmm_model: Optional[GaussianHMM] = None
        self.is_trained = False
        self.regime_history: List[MarketRegime] = []
        self.logger = logging.getLogger(__name__)

    def detect_regime_rules(self, df: pd.DataFrame) -> Tuple[MarketRegime, Dict[str, float]]:
        """
        Rule-based regime detection.

        Args:
            df: DataFrame with OHLCV data (needs at least 200+ bars)

        Returns:
            Tuple of (regime, confidence_scores)
        """
        close = df['close']
        high = df['high']
        low = df['low']

        # Calculate indicators
        ma_fast = sma(close, self.config.ma_fast)
        ma_slow = sma(close, self.config.ma_slow)
        adx_line, plus_di, minus_di = adx(high, low, close, 14)
        momentum = roc(close, self.config.momentum_period)

        # Get latest values
        latest_close = close.iloc[-1]
        latest_ma_fast = ma_fast.iloc[-1]
        latest_ma_slow = ma_slow.iloc[-1]
        latest_adx = adx_line.iloc[-1]
        latest_momentum = momentum.iloc[-1]
        latest_plus_di = plus_di.iloc[-1]
        latest_minus_di = minus_di.iloc[-1]

        # Check for correction (sharp drop in recent bars)
        if len(close) >= self.config.correction_lookback:
            recent_high = close.iloc[-self.config.correction_lookback:].max()
            recent_drop = ((latest_close - recent_high) / recent_high) * 100

            if recent_drop < self.config.correction_threshold:
                # Correction detected
                confidence = min(abs(recent_drop) / 20.0, 1.0)  # Normalize
                return MarketRegime.CORRECTION, {
                    'bull': 0.1,
                    'bear': 0.3,
                    'sideways': 0.1,
                    'correction': confidence
                }

        # Calculate regime scores
        scores = {
            'bull': 0.0,
            'bear': 0.0,
            'sideways': 0.0,
            'correction': 0.0
        }

        # Price vs MA200
        if latest_close > latest_ma_slow:
            scores['bull'] += 0.3
        else:
            scores['bear'] += 0.3

        # Price vs MA50
        if latest_close > latest_ma_fast:
            scores['bull'] += 0.2
        else:
            scores['bear'] += 0.2

        # MA alignment
        if latest_ma_fast > latest_ma_slow:
            scores['bull'] += 0.1
        else:
            scores['bear'] += 0.1

        # ADX - trend strength
        if latest_adx < self.config.adx_sideways_threshold:
            scores['sideways'] += 0.4
        elif latest_adx > self.config.adx_trend_threshold:
            # Strong trend - boost bull or bear based on DI
            if latest_plus_di > latest_minus_di:
                scores['bull'] += 0.2
            else:
                scores['bear'] += 0.2

        # Momentum
        if latest_momentum > self.config.momentum_bull_threshold:
            scores['bull'] += 0.2
        elif latest_momentum < self.config.momentum_bear_threshold:
            scores['bear'] += 0.2
        else:
            scores['sideways'] += 0.2

        # Normalize scores
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        # Select regime with highest score
        regime_name = max(scores, key=scores.get)
        regime = MarketRegime(regime_name)

        return regime, scores

    def train_hmm(self, df: pd.DataFrame) -> None:
        """
        Train HMM model on historical data.

        Args:
            df: DataFrame with OHLCV data
        """
        if not HMM_AVAILABLE:
            self.logger.warning("HMM not available, skipping training")
            return

        # Generate features for HMM
        features = self._prepare_hmm_features(df)

        # Remove NaN
        features_clean = features.dropna()

        if len(features_clean) < 100:
            self.logger.warning("Not enough data for HMM training")
            return

        X = features_clean.values

        # Initialize and train HMM
        self.hmm_model = GaussianHMM(
            n_components=self.config.hmm_n_states,
            covariance_type=self.config.hmm_covariance_type,
            n_iter=self.config.hmm_n_iter,
            random_state=42
        )

        try:
            self.hmm_model.fit(X)
            self.is_trained = True
            self.logger.info(f"HMM trained successfully with {len(X)} samples")
        except Exception as e:
            self.logger.error(f"HMM training failed: {e}")
            self.is_trained = False

    def _prepare_hmm_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for HMM - must match training features."""
        close = df['close']
        high = df['high']
        low = df['low']

        features = pd.DataFrame(index=df.index)

        # Same features as training: price_vs_ma200, adx, roc_20, atr_pct, drawdown
        ma200 = sma(close, 200)
        features['price_vs_ma200'] = (close - ma200) / ma200

        adx_line, _, _ = adx(high, low, close, 14)
        features['adx'] = adx_line / 100  # Normalize to 0-1

        features['roc_20'] = roc(close, 20) / 100  # Normalize

        atr_val = atr(high, low, close, 14)
        features['atr_pct'] = atr_val / close

        # Drawdown from rolling max
        rolling_max = close.rolling(window=50, min_periods=1).max()
        features['drawdown'] = (close - rolling_max) / rolling_max

        return features

    def detect_regime_hmm(self, df: pd.DataFrame) -> Tuple[int, np.ndarray]:
        """
        Detect regime using HMM.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Tuple of (state_index, state_probabilities)
        """
        if not self.is_trained or self.hmm_model is None:
            return 0, np.array([0.25, 0.25, 0.25, 0.25])

        features = self._prepare_hmm_features(df)
        features_clean = features.dropna()

        if len(features_clean) == 0:
            return 0, np.array([0.25, 0.25, 0.25, 0.25])

        X = features_clean.values

        try:
            # Get most likely state sequence
            state_sequence = self.hmm_model.predict(X)
            current_state = state_sequence[-1]

            # Get state probabilities for current observation
            log_prob, state_probs = self.hmm_model.score_samples(X[-1:])
            probs = np.exp(state_probs[0])  # Convert from log

            return current_state, probs
        except Exception as e:
            self.logger.error(f"HMM prediction failed: {e}")
            return 0, np.array([0.25, 0.25, 0.25, 0.25])

    def _map_hmm_state_to_regime(self,
                                  state: int,
                                  df: pd.DataFrame) -> MarketRegime:
        """
        Map HMM state to market regime.

        Uses feature characteristics to interpret HMM states.
        """
        # Get current market characteristics
        close = df['close']
        high = df['high']
        low = df['low']

        ma200 = sma(close, 200)
        adx_line, _, _ = adx(high, low, close, 14)
        momentum = roc(close, 20)

        above_ma200 = close.iloc[-1] > ma200.iloc[-1]
        strong_trend = adx_line.iloc[-1] > 25
        positive_momentum = momentum.iloc[-1] > 0

        # Interpret state based on market context
        if strong_trend:
            if positive_momentum and above_ma200:
                return MarketRegime.BULL
            elif not positive_momentum and not above_ma200:
                return MarketRegime.BEAR
        else:
            return MarketRegime.SIDEWAYS

        # Default mapping based on state index
        state_map = {
            0: MarketRegime.BULL,
            1: MarketRegime.BEAR,
            2: MarketRegime.SIDEWAYS,
            3: MarketRegime.CORRECTION
        }
        return state_map.get(state, MarketRegime.SIDEWAYS)

    def detect(self, df: pd.DataFrame) -> Tuple[MarketRegime, Dict[str, float]]:
        """
        Detect market regime using hybrid approach.

        Combines rule-based and HMM predictions.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Tuple of (regime, confidence_scores)
        """
        # Rule-based detection
        rule_regime, rule_scores = self.detect_regime_rules(df)

        # If HMM is trained, combine predictions
        if self.is_trained and HMM_AVAILABLE:
            hmm_state, hmm_probs = self.detect_regime_hmm(df)
            hmm_regime = self._map_hmm_state_to_regime(hmm_state, df)

            # Combine scores
            combined_scores = {}
            regime_list = ['bull', 'bear', 'sideways', 'correction']

            for i, regime_name in enumerate(regime_list):
                rule_score = rule_scores.get(regime_name, 0)
                hmm_score = hmm_probs[i] if i < len(hmm_probs) else 0

                combined_scores[regime_name] = (
                    self.config.rule_weight * rule_score +
                    self.config.hmm_weight * hmm_score
                )

            # Normalize
            total = sum(combined_scores.values())
            if total > 0:
                combined_scores = {k: v / total for k, v in combined_scores.items()}

            final_regime_name = max(combined_scores, key=combined_scores.get)
            final_regime = MarketRegime(final_regime_name)

            # Store history
            self.regime_history.append(final_regime)

            return final_regime, combined_scores

        # Store history
        self.regime_history.append(rule_regime)

        return rule_regime, rule_scores

    def get_regime_duration(self) -> int:
        """Get number of bars in current regime."""
        if not self.regime_history:
            return 0

        current = self.regime_history[-1]
        duration = 0

        for regime in reversed(self.regime_history):
            if regime == current:
                duration += 1
            else:
                break

        return duration

    def get_regime_transitions(self) -> Dict[str, int]:
        """Count regime transitions in history."""
        if len(self.regime_history) < 2:
            return {}

        transitions = {}
        for i in range(1, len(self.regime_history)):
            prev = self.regime_history[i-1].value
            curr = self.regime_history[i].value

            if prev != curr:
                key = f"{prev}_to_{curr}"
                transitions[key] = transitions.get(key, 0) + 1

        return transitions

    def save_model(self, path: str) -> None:
        """Save trained HMM model."""
        if self.hmm_model is None:
            self.logger.warning("No model to save")
            return

        try:
            import joblib
            joblib.dump({
                'model': self.hmm_model,
                'config': self.config,
                'is_trained': self.is_trained
            }, path)
            self.logger.info(f"Model saved to {path}")
        except Exception as e:
            self.logger.error(f"Failed to save model: {e}")

    def load_model(self, path: str) -> None:
        """Load trained HMM model."""
        try:
            import joblib
            data = joblib.load(path)
            self.hmm_model = data['model']
            self.config = data.get('config', self.config)
            self.is_trained = data.get('is_trained', True)
            self.logger.info(f"Model loaded from {path}")
        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")


def detect_regime_simple(df: pd.DataFrame) -> MarketRegime:
    """
    Simple regime detection without class instantiation.

    Useful for quick checks.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        MarketRegime
    """
    detector = RegimeDetector()
    regime, _ = detector.detect_regime_rules(df)
    return regime
