"""
Train the XGBoost strategy selector model.

Uses walk-forward validation and early stopping to prevent overfitting.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import argparse
import joblib

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.strategy_selector import StrategySelector, SelectorConfig, StrategyType
from src.ml.validation import WalkForwardValidator, WalkForwardConfig


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_features(features_path: str, labels_path: str) -> Tuple[pd.DataFrame, pd.Series]:
    """Load features and labels."""
    features = pd.read_parquet(features_path)
    labels = pd.read_parquet(labels_path)['label']

    # Align
    common_idx = features.index.intersection(labels.index)
    features = features.loc[common_idx]
    labels = labels.loc[common_idx]

    # Drop rows with missing labels
    valid_mask = labels.notna()
    features = features[valid_mask]
    labels = labels[valid_mask]

    logger.info(f"Loaded {len(features)} labeled samples")

    return features, labels


def prepare_features(features: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    """
    Prepare features for XGBoost.

    Returns:
        Tuple of (feature_array, feature_names)
    """
    # Select relevant features
    feature_cols = [col for col in features.columns if not col.startswith('_')]

    # Handle missing values
    X = features[feature_cols].fillna(0)

    # Handle infinite values
    X = X.replace([np.inf, -np.inf], 0)

    logger.info(f"Feature matrix shape: {X.shape}")

    return X.values, feature_cols


def train_xgboost_model(X: np.ndarray,
                        y: np.ndarray,
                        config: Optional[SelectorConfig] = None) -> StrategySelector:
    """
    Train XGBoost strategy selector.

    Args:
        X: Feature matrix
        y: Strategy labels (0-7)
        config: Selector configuration

    Returns:
        Trained StrategySelector
    """
    config = config or SelectorConfig(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        min_child_weight=3,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0
    )

    selector = StrategySelector(config)

    # Split for validation (last 20%)
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    # Train
    metrics = selector.train(X_train, y_train, X_val, y_val)
    logger.info(f"Training metrics: {metrics}")

    return selector


def run_walk_forward_validation(X: np.ndarray,
                                 y: np.ndarray,
                                 config: Optional[SelectorConfig] = None) -> Dict:
    """
    Run walk-forward validation for the strategy selector.

    Returns:
        Validation results
    """
    wf_config = WalkForwardConfig(
        train_window=1095,  # ~6 months at 4h
        test_window=180,    # ~1 month at 4h
        step_size=180,
        purge_window=10
    )

    validator = WalkForwardValidator(wf_config)

    selector_config = config or SelectorConfig(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1
    )

    def train_func(X_train, y_train):
        try:
            import xgboost as xgb
            model = xgb.XGBClassifier(
                n_estimators=selector_config.n_estimators,
                max_depth=selector_config.max_depth,
                learning_rate=selector_config.learning_rate,
                min_child_weight=selector_config.min_child_weight,
                subsample=selector_config.subsample,
                colsample_bytree=selector_config.colsample_bytree,
                reg_alpha=selector_config.reg_alpha,
                reg_lambda=selector_config.reg_lambda,
                objective='multi:softprob',
                num_class=len(StrategyType),
                eval_metric='mlogloss',
                random_state=42,
                verbosity=0
            )
            model.fit(X_train, y_train)
            return model
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return None

    def predict_func(model, X_test):
        if model is None:
            return np.zeros(len(X_test))
        return model.predict(X_test)

    metrics = validator.validate(X, y, train_func, predict_func)
    logger.info(f"Walk-forward validation metrics: {metrics}")

    stability = validator.analyze_stability()
    logger.info(f"Model stability: {stability}")

    return {
        'metrics': metrics,
        'stability': stability,
        'fold_details': validator.get_fold_details()
    }


def analyze_feature_importance(selector: StrategySelector, feature_names: List[str]) -> pd.DataFrame:
    """Analyze and display feature importance."""
    importance = selector.get_feature_importance()

    if not importance:
        logger.warning("No feature importance available")
        return pd.DataFrame()

    # Create DataFrame
    if len(feature_names) == len(importance):
        df = pd.DataFrame({
            'feature': feature_names,
            'importance': list(importance.values())
        })
    else:
        df = pd.DataFrame({
            'feature': list(importance.keys()),
            'importance': list(importance.values())
        })

    df = df.sort_values('importance', ascending=False)

    logger.info("Top 20 features by importance:")
    for _, row in df.head(20).iterrows():
        logger.info(f"  {row['feature']}: {row['importance']:.4f}")

    return df


def create_synthetic_labels(features: pd.DataFrame,
                            random_seed: int = 42) -> pd.Series:
    """
    Create synthetic labels for testing when real labels aren't available.

    This simulates the strategy selection labels based on feature values.
    In production, labels should be generated from actual backtest results.
    """
    np.random.seed(random_seed)

    labels = []

    for i in range(len(features)):
        row = features.iloc[i]

        # Simple heuristic-based labeling
        adx = row.get('adx', 25)
        rsi = row.get('rsi', 50)
        trend = row.get('price_vs_ma200', 0)

        # High ADX + trend = trend following
        if adx > 30 and abs(trend) > 0.05:
            if trend > 0:
                label = StrategyType.TREND_FOLLOW.value  # Trend follow
            else:
                label = StrategyType.TREND_FOLLOW.value  # Trend follow (short)
        # Low ADX = mean reversion
        elif adx < 20:
            label = StrategyType.RSI_REVERSAL.value  # RSI reversal
        # Medium conditions
        elif rsi < 30 or rsi > 70:
            label = StrategyType.RSI_REVERSAL.value
        else:
            label = StrategyType.EMA_CROSS.value  # EMA cross

        labels.append(label)

    return pd.Series(labels, index=features.index)


def save_model(selector: StrategySelector, output_path: str):
    """Save trained model."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    selector.save_model(output_path)
    logger.info(f"Model saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Train strategy selector model')
    parser.add_argument('--features', required=True, help='Path to features parquet')
    parser.add_argument('--labels', help='Path to labels parquet (optional, will generate synthetic if not provided)')
    parser.add_argument('--output', default='models/strategy_xgb.pkl', help='Output model path')
    parser.add_argument('--validate', action='store_true', help='Run walk-forward validation')
    parser.add_argument('--importance', action='store_true', help='Analyze feature importance')

    args = parser.parse_args()

    # Load features
    features = pd.read_parquet(args.features)
    features = features.fillna(0).replace([np.inf, -np.inf], 0)

    # Load or generate labels
    if args.labels:
        labels_df = pd.read_parquet(args.labels)
        labels = labels_df['label']
    else:
        logger.info("Generating synthetic labels for training...")
        labels = create_synthetic_labels(features)

    # Align features and labels
    common_idx = features.index.intersection(labels.index)
    features = features.loc[common_idx]
    labels = labels.loc[common_idx]

    # Drop NaN labels
    valid_mask = labels.notna()
    features = features[valid_mask]
    labels = labels[valid_mask].astype(int)

    logger.info(f"Training with {len(features)} samples")
    logger.info(f"Label distribution:\n{labels.value_counts().sort_index()}")

    # Prepare features
    X, feature_names = prepare_features(features)
    y = labels.values

    # Walk-forward validation
    if args.validate:
        logger.info("Running walk-forward validation...")
        validation_results = run_walk_forward_validation(X, y)

        # Save results
        results_path = Path(args.output).parent / 'selector_validation_results.csv'
        if 'fold_details' in validation_results:
            validation_results['fold_details'].to_csv(results_path, index=False)
            logger.info(f"Validation results saved to {results_path}")

    # Train final model
    logger.info("Training final model on all data...")
    selector = train_xgboost_model(X, y)
    selector.feature_names = feature_names

    # Feature importance
    if args.importance:
        importance_df = analyze_feature_importance(selector, feature_names)
        importance_path = Path(args.output).parent / 'feature_importance.csv'
        importance_df.to_csv(importance_path, index=False)
        logger.info(f"Feature importance saved to {importance_path}")

    # Save model
    save_model(selector, args.output)

    logger.info("Training complete!")


if __name__ == '__main__':
    main()
