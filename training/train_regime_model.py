"""
Train the Hidden Markov Model for regime detection.

Uses walk-forward validation to avoid overfitting.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Tuple
import logging
import argparse
import joblib

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.regime_detector import RegimeDetector, RegimeConfig, MarketRegime
from src.ml.validation import WalkForwardValidator, WalkForwardConfig


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_features(features_path: str, labels_path: str) -> Tuple[pd.DataFrame, pd.Series]:
    """Load features and labels from parquet files."""
    features = pd.read_parquet(features_path)
    labels = pd.read_parquet(labels_path)['label']

    # Align indices
    common_idx = features.index.intersection(labels.index)
    features = features.loc[common_idx]
    labels = labels.loc[common_idx]

    logger.info(f"Loaded {len(features)} samples")

    return features, labels


def train_hmm_model(features: pd.DataFrame,
                    labels: pd.Series,
                    config: Optional[RegimeConfig] = None) -> RegimeDetector:
    """
    Train HMM model for regime detection.

    Args:
        features: Feature DataFrame
        labels: Regime labels
        config: Regime detector configuration

    Returns:
        Trained RegimeDetector
    """
    # Create detector
    detector = RegimeDetector(config)

    # Prepare features
    # Select HMM-relevant features
    hmm_features = ['price_vs_ma200', 'adx', 'roc_20', 'atr_pct', 'drawdown']
    available_features = [f for f in hmm_features if f in features.columns]

    X = features[available_features].dropna()

    if len(X) < 500:
        logger.warning(f"Only {len(X)} samples available after dropping NaN")

    # Create a mock DataFrame for HMM training (need OHLCV structure)
    # The RegimeDetector.train_hmm expects OHLCV data
    # We'll directly train the HMM here instead

    try:
        from hmmlearn.hmm import GaussianHMM

        hmm_model = GaussianHMM(
            n_components=4,
            covariance_type="diag",
            n_iter=100,
            random_state=42
        )

        hmm_model.fit(X.values)
        detector.hmm_model = hmm_model
        detector.is_trained = True

        logger.info("HMM model trained successfully")

        # Log state statistics
        states = hmm_model.predict(X.values)
        for state in range(4):
            count = (states == state).sum()
            pct = count / len(states) * 100
            logger.info(f"State {state}: {count} samples ({pct:.1f}%)")

    except Exception as e:
        logger.error(f"HMM training failed: {e}")

    return detector


def validate_model(features: pd.DataFrame,
                   labels: pd.Series,
                   config: Optional[RegimeConfig] = None) -> Dict:
    """
    Validate regime model using walk-forward validation.

    Returns:
        Validation metrics
    """
    wf_config = WalkForwardConfig(
        train_window=1095,  # ~6 months at 4h
        test_window=180,    # ~1 month at 4h
        step_size=180
    )

    validator = WalkForwardValidator(wf_config)

    # Select features
    hmm_features = ['price_vs_ma200', 'adx', 'roc_20', 'atr_pct', 'drawdown']
    available_features = [f for f in hmm_features if f in features.columns]

    X = features[available_features].fillna(0).values

    # Encode labels
    label_map = {'bull': 0, 'bear': 1, 'sideways': 2, 'correction': 3}
    y = labels.map(lambda x: label_map.get(x, 2) if pd.notna(x) else 2).values

    def train_func(X_train, y_train):
        from hmmlearn.hmm import GaussianHMM
        model = GaussianHMM(
            n_components=4,
            covariance_type="diag",
            n_iter=50,
            random_state=42
        )
        model.fit(X_train)
        return model

    def predict_func(model, X_test):
        return model.predict(X_test)

    try:
        metrics = validator.validate(X, y, train_func, predict_func)
        logger.info(f"Validation metrics: {metrics}")

        # Stability analysis
        stability = validator.analyze_stability()
        logger.info(f"Stability analysis: {stability}")

        return {
            'metrics': metrics,
            'stability': stability,
            'fold_details': validator.get_fold_details()
        }
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return {'error': str(e)}


def save_model(detector: RegimeDetector, output_path: str):
    """Save trained model."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    detector.save_model(output_path)
    logger.info(f"Model saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Train regime detection model')
    parser.add_argument('--features', required=True, help='Path to features parquet')
    parser.add_argument('--labels', required=True, help='Path to labels parquet')
    parser.add_argument('--output', default='models/regime_hmm.pkl', help='Output model path')
    parser.add_argument('--validate', action='store_true', help='Run walk-forward validation')

    args = parser.parse_args()

    # Load data
    features, labels = load_features(args.features, args.labels)

    # Validate if requested
    if args.validate:
        logger.info("Running walk-forward validation...")
        validation_results = validate_model(features, labels)

        # Save validation results
        results_path = Path(args.output).parent / 'regime_validation_results.csv'
        if 'fold_details' in validation_results:
            validation_results['fold_details'].to_csv(results_path, index=False)
            logger.info(f"Validation results saved to {results_path}")

    # Train final model on all data
    logger.info("Training final model...")
    detector = train_hmm_model(features, labels)

    # Save model
    save_model(detector, args.output)

    logger.info("Training complete!")


if __name__ == '__main__':
    main()
