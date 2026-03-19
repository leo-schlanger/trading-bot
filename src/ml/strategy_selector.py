"""
Strategy Selector using XGBoost.

Selects the best trading strategy based on current market conditions
using a trained classification model.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import IntEnum
import logging

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logging.warning("xgboost not installed. Strategy selection will use fallback.")

import sys
sys.path.insert(0, str(__file__).replace('\\', '/').rsplit('/src/', 1)[0])

from src.ml.features import FeatureGenerator
from src.ml.regime_detector import MarketRegime


class StrategyType(IntEnum):
    """Available trading strategies."""
    EMA_CROSS = 0
    RSI_REVERSAL = 1
    TREND_FOLLOW = 2
    HULL_MA = 3
    KELTNER_SQUEEZE = 4
    WILLIAMS_RSI = 5
    DONCHIAN_BREAKOUT = 6
    MOMENTUM = 7


STRATEGY_NAMES = {
    StrategyType.EMA_CROSS: "EMA Crossover",
    StrategyType.RSI_REVERSAL: "RSI Mean Reversion",
    StrategyType.TREND_FOLLOW: "Trend Following (Supertrend)",
    StrategyType.HULL_MA: "Hull Moving Average",
    StrategyType.KELTNER_SQUEEZE: "Keltner Channel Squeeze",
    StrategyType.WILLIAMS_RSI: "Williams %R + RSI",
    StrategyType.DONCHIAN_BREAKOUT: "Donchian Breakout",
    StrategyType.MOMENTUM: "Momentum Strategy"
}

# Strategy characteristics for fallback selection
STRATEGY_REGIME_AFFINITY = {
    MarketRegime.BULL: [
        StrategyType.TREND_FOLLOW,
        StrategyType.EMA_CROSS,
        StrategyType.MOMENTUM,
        StrategyType.DONCHIAN_BREAKOUT
    ],
    MarketRegime.BEAR: [
        StrategyType.TREND_FOLLOW,
        StrategyType.RSI_REVERSAL,
        StrategyType.HULL_MA
    ],
    MarketRegime.SIDEWAYS: [
        StrategyType.RSI_REVERSAL,
        StrategyType.KELTNER_SQUEEZE,
        StrategyType.WILLIAMS_RSI
    ],
    MarketRegime.CORRECTION: [
        StrategyType.RSI_REVERSAL,
        StrategyType.WILLIAMS_RSI
    ]
}


@dataclass
class SelectorConfig:
    """Configuration for strategy selector."""
    # XGBoost parameters
    n_estimators: int = 100
    max_depth: int = 5
    learning_rate: float = 0.1
    min_child_weight: int = 3
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0

    # Feature settings
    lookback_bars: int = 20
    min_confidence: float = 0.3  # Minimum confidence for selection

    # Fallback behavior
    use_regime_fallback: bool = True


class StrategySelector:
    """
    XGBoost-based strategy selector.

    Input features:
    - Last N bars of price/indicator data
    - Current market regime (one-hot encoded)
    - Volatility metrics

    Output:
    - Best strategy (0-7)
    - Confidence score
    """

    def __init__(self, config: Optional[SelectorConfig] = None):
        self.config = config or SelectorConfig()
        self.feature_generator = FeatureGenerator()
        self.model: Optional[xgb.XGBClassifier] = None
        self.is_trained = False
        self.feature_names: List[str] = []
        self.logger = logging.getLogger(__name__)

    def _prepare_features(self,
                          df: pd.DataFrame,
                          regime: MarketRegime) -> np.ndarray:
        """
        Prepare features for strategy selection.

        Args:
            df: DataFrame with OHLCV data
            regime: Current market regime

        Returns:
            Feature array
        """
        # Get strategy-specific features
        features_df = self.feature_generator.get_strategy_features(
            df, lookback=self.config.lookback_bars
        )

        # Get latest feature values
        if len(features_df) < 1:
            return np.array([])

        latest_features = features_df.iloc[-1:].copy()

        # Add regime as one-hot encoded
        for r in MarketRegime:
            latest_features[f'regime_{r.value}'] = 1 if regime == r else 0

        # Add volatility context
        close = df['close']
        volatility_current = close.pct_change().iloc[-20:].std() if len(close) >= 20 else 0
        volatility_mean = close.pct_change().rolling(100).std().iloc[-1] if len(close) >= 100 else volatility_current

        latest_features['volatility_ratio'] = (
            volatility_current / volatility_mean if volatility_mean > 0 else 1.0
        )

        # Store feature names if not set
        if not self.feature_names:
            self.feature_names = latest_features.columns.tolist()

        # Handle NaN
        latest_features = latest_features.fillna(0)

        return latest_features.values.flatten()

    def train(self,
              X: np.ndarray,
              y: np.ndarray,
              X_val: Optional[np.ndarray] = None,
              y_val: Optional[np.ndarray] = None) -> Dict[str, float]:
        """
        Train the strategy selector model.

        Args:
            X: Training features
            y: Training labels (strategy indices)
            X_val: Validation features (optional)
            y_val: Validation labels (optional)

        Returns:
            Dict of training metrics
        """
        if not XGBOOST_AVAILABLE:
            self.logger.error("XGBoost not available")
            return {'error': 'xgboost not installed'}

        # Initialize model
        self.model = xgb.XGBClassifier(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            min_child_weight=self.config.min_child_weight,
            subsample=self.config.subsample,
            colsample_bytree=self.config.colsample_bytree,
            reg_alpha=self.config.reg_alpha,
            reg_lambda=self.config.reg_lambda,
            objective='multi:softprob',
            num_class=len(StrategyType),
            eval_metric='mlogloss',
            random_state=42,
            use_label_encoder=False
        )

        # Prepare evaluation set if validation data provided
        eval_set = [(X, y)]
        if X_val is not None and y_val is not None:
            eval_set.append((X_val, y_val))

        # Train with early stopping
        try:
            self.model.fit(
                X, y,
                eval_set=eval_set,
                verbose=False
            )

            self.is_trained = True

            # Calculate metrics
            train_preds = self.model.predict(X)
            train_accuracy = (train_preds == y).mean()

            metrics = {
                'train_accuracy': train_accuracy,
                'n_samples': len(X),
                'n_features': X.shape[1] if len(X.shape) > 1 else 1
            }

            if X_val is not None:
                val_preds = self.model.predict(X_val)
                metrics['val_accuracy'] = (val_preds == y_val).mean()

            self.logger.info(f"Model trained: {metrics}")
            return metrics

        except Exception as e:
            self.logger.error(f"Training failed: {e}")
            return {'error': str(e)}

    def select_strategy(self,
                        df: pd.DataFrame,
                        regime: MarketRegime) -> Tuple[StrategyType, float, Dict[str, float]]:
        """
        Select the best strategy for current conditions.

        Args:
            df: DataFrame with OHLCV data
            regime: Current market regime

        Returns:
            Tuple of (strategy, confidence, all_probabilities)
        """
        # Prepare features
        features = self._prepare_features(df, regime)

        if len(features) == 0:
            return self._fallback_selection(regime)

        # If model is trained, use it
        if self.is_trained and self.model is not None:
            try:
                features_2d = features.reshape(1, -1)
                probabilities = self.model.predict_proba(features_2d)[0]

                best_idx = np.argmax(probabilities)
                confidence = probabilities[best_idx]

                # Create probability dict
                prob_dict = {
                    STRATEGY_NAMES[StrategyType(i)]: p
                    for i, p in enumerate(probabilities)
                }

                strategy = StrategyType(best_idx)

                # Check confidence threshold
                if confidence < self.config.min_confidence:
                    self.logger.warning(
                        f"Low confidence ({confidence:.2f}), using fallback"
                    )
                    if self.config.use_regime_fallback:
                        return self._fallback_selection(regime)

                return strategy, confidence, prob_dict

            except Exception as e:
                self.logger.error(f"Prediction failed: {e}")
                return self._fallback_selection(regime)

        # No trained model, use fallback
        return self._fallback_selection(regime)

    def _fallback_selection(self,
                            regime: MarketRegime) -> Tuple[StrategyType, float, Dict[str, float]]:
        """
        Fallback strategy selection based on regime affinity.

        Args:
            regime: Current market regime

        Returns:
            Tuple of (strategy, confidence, probabilities)
        """
        preferred_strategies = STRATEGY_REGIME_AFFINITY.get(
            regime, [StrategyType.EMA_CROSS]
        )

        # Select first preferred strategy
        strategy = preferred_strategies[0] if preferred_strategies else StrategyType.EMA_CROSS

        # Create pseudo-probabilities
        prob_dict = {}
        for st in StrategyType:
            if st in preferred_strategies:
                idx = preferred_strategies.index(st)
                prob_dict[STRATEGY_NAMES[st]] = 1.0 / (idx + 1) / len(preferred_strategies)
            else:
                prob_dict[STRATEGY_NAMES[st]] = 0.05

        # Normalize
        total = sum(prob_dict.values())
        prob_dict = {k: v / total for k, v in prob_dict.items()}

        confidence = prob_dict[STRATEGY_NAMES[strategy]]

        self.logger.info(f"Fallback selection: {STRATEGY_NAMES[strategy]} (regime={regime.value})")

        return strategy, confidence, prob_dict

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from trained model."""
        if not self.is_trained or self.model is None:
            return {}

        try:
            importance = self.model.feature_importances_

            if len(self.feature_names) == len(importance):
                return dict(zip(self.feature_names, importance))
            else:
                return {f'feature_{i}': imp for i, imp in enumerate(importance)}
        except Exception as e:
            self.logger.error(f"Failed to get feature importance: {e}")
            return {}

    def save_model(self, path: str) -> None:
        """Save trained model to file."""
        if self.model is None:
            self.logger.warning("No model to save")
            return

        try:
            import joblib
            joblib.dump({
                'model': self.model,
                'config': self.config,
                'feature_names': self.feature_names,
                'is_trained': self.is_trained
            }, path)
            self.logger.info(f"Model saved to {path}")
        except Exception as e:
            self.logger.error(f"Failed to save model: {e}")

    def load_model(self, path: str) -> None:
        """Load trained model from file."""
        try:
            import joblib
            data = joblib.load(path)
            self.model = data['model']
            self.config = data.get('config', self.config)
            self.feature_names = data.get('feature_names', [])
            self.is_trained = data.get('is_trained', True)
            self.logger.info(f"Model loaded from {path}")
        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")


def get_strategy_recommendation(df: pd.DataFrame,
                                 regime: MarketRegime) -> Tuple[str, float]:
    """
    Quick strategy recommendation without instantiation.

    Args:
        df: DataFrame with OHLCV data
        regime: Current market regime

    Returns:
        Tuple of (strategy_name, confidence)
    """
    selector = StrategySelector()
    strategy, confidence, _ = selector.select_strategy(df, regime)
    return STRATEGY_NAMES[strategy], confidence
