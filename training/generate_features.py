"""
Generate features for ML model training.

Processes historical OHLCV data and generates features for:
- Regime detection
- Strategy selection
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime
import argparse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.features import FeatureGenerator, FeatureConfig
from src.ml.regime_detector import RegimeDetector, MarketRegime
from src.indicators.technical import atr, sma


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_data(data_path: str) -> pd.DataFrame:
    """
    Load OHLCV data from CSV.

    Expected format:
    - Index: datetime
    - Columns: open, high, low, close, volume
    """
    df = pd.read_csv(data_path, index_col=0, parse_dates=True)

    # Ensure required columns
    required = ['open', 'high', 'low', 'close', 'volume']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Sort by date
    df = df.sort_index()

    logger.info(f"Loaded {len(df)} bars from {data_path}")
    logger.info(f"Date range: {df.index[0]} to {df.index[-1]}")

    return df


def generate_regime_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Generate features for regime detection model.

    Returns:
        Tuple of (features_df, labels)
    """
    feature_gen = FeatureGenerator()
    regime_detector = RegimeDetector()

    # Generate features
    features = feature_gen.get_regime_features(df)

    # Generate labels (regime for each bar)
    labels = []

    for i in range(len(df)):
        if i < 200:
            labels.append(None)
            continue

        # Get regime for this bar using historical data only
        lookback = df.iloc[max(0, i-200):i+1]
        regime, _ = regime_detector.detect_regime_rules(lookback)
        labels.append(regime.value)

    labels_series = pd.Series(labels, index=df.index)

    logger.info(f"Generated regime features: {features.shape}")
    logger.info(f"Regime distribution: {labels_series.value_counts()}")

    return features, labels_series


def generate_strategy_features(df: pd.DataFrame,
                                lookback_window: int = 20) -> pd.DataFrame:
    """
    Generate features for strategy selection model.

    Returns:
        DataFrame with strategy selection features
    """
    feature_gen = FeatureGenerator()

    # Generate all features
    features = feature_gen.generate_features(df)

    # Add rolling window aggregations for key features
    key_features = ['rsi', 'adx', 'atr_pct', 'macd_histogram', 'bb_position']

    for feat in key_features:
        if feat in features.columns:
            features[f'{feat}_mean_{lookback_window}'] = features[feat].rolling(lookback_window).mean()
            features[f'{feat}_std_{lookback_window}'] = features[feat].rolling(lookback_window).std()
            features[f'{feat}_min_{lookback_window}'] = features[feat].rolling(lookback_window).min()
            features[f'{feat}_max_{lookback_window}'] = features[feat].rolling(lookback_window).max()

    logger.info(f"Generated strategy features: {features.shape}")

    return features


def generate_strategy_labels(df: pd.DataFrame,
                             strategies: Dict[str, 'BaseStrategy'],
                             forward_window: int = 20) -> pd.Series:
    """
    Generate labels for strategy selection.

    For each bar, the label is the strategy that performed best
    over the next forward_window bars.

    Args:
        df: OHLCV data
        strategies: Dict of strategy_name -> strategy instance
        forward_window: Bars to evaluate performance

    Returns:
        Series of best strategy indices
    """
    from src.backtest.engine import BacktestEngine, BacktestConfig

    labels = []
    config = BacktestConfig(initial_capital=10000, risk_per_trade=0.02)

    for i in range(len(df) - forward_window):
        if i < 200:  # Need warmup period
            labels.append(None)
            continue

        if i % 500 == 0:
            logger.info(f"Evaluating strategies at bar {i}/{len(df)}")

        # Evaluate each strategy over the next window
        window_data = df.iloc[i:i+forward_window+1]
        best_strategy = None
        best_return = -np.inf

        for strat_idx, (strat_name, strategy) in enumerate(strategies.items()):
            try:
                engine = BacktestEngine(config)
                result = engine.run(window_data, strategy, verbose=False)
                final_return = (result['equity_curve'].iloc[-1] / config.initial_capital) - 1

                if final_return > best_return:
                    best_return = final_return
                    best_strategy = strat_idx
            except Exception as e:
                continue

        labels.append(best_strategy)

    # Pad end with None
    labels.extend([None] * forward_window)

    return pd.Series(labels, index=df.index)


def save_features(features: pd.DataFrame,
                   labels: pd.Series,
                   output_dir: str,
                   prefix: str):
    """Save features and labels to files."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    features_file = output_path / f'{prefix}_features.parquet'
    labels_file = output_path / f'{prefix}_labels.parquet'

    features.to_parquet(features_file)
    labels.to_frame('label').to_parquet(labels_file)

    logger.info(f"Saved features to {features_file}")
    logger.info(f"Saved labels to {labels_file}")


def main():
    parser = argparse.ArgumentParser(description='Generate ML features')
    parser.add_argument('--data', required=True, help='Path to OHLCV CSV file')
    parser.add_argument('--output', default='data/processed', help='Output directory')
    parser.add_argument('--asset', default='BTC', help='Asset name for file prefix')
    parser.add_argument('--type', choices=['regime', 'strategy', 'both'], default='both',
                        help='Type of features to generate')

    args = parser.parse_args()

    # Load data
    df = load_data(args.data)

    if args.type in ['regime', 'both']:
        logger.info("Generating regime features...")
        regime_features, regime_labels = generate_regime_features(df)
        save_features(
            regime_features,
            regime_labels,
            args.output,
            f'{args.asset}_regime'
        )

    if args.type in ['strategy', 'both']:
        logger.info("Generating strategy features...")
        strategy_features = generate_strategy_features(df)

        # Note: Strategy labels require running backtests for each strategy
        # This is computationally expensive and typically done separately
        logger.info("Strategy features generated. Run separate labeling script for strategy labels.")

        # Save features only (labels need separate generation)
        output_path = Path(args.output)
        output_path.mkdir(parents=True, exist_ok=True)
        strategy_features.to_parquet(output_path / f'{args.asset}_strategy_features.parquet')

    logger.info("Feature generation complete!")


if __name__ == '__main__':
    main()
