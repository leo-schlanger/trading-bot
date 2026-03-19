"""
Walk-Forward Validation for time-series ML models.

Implements proper out-of-sample testing to avoid overfitting.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward validation."""
    # Window sizes (in bars)
    train_window: int = 1095  # ~6 months at 4h = 6*30*6 bars
    test_window: int = 180    # ~1 month at 4h
    step_size: int = 180      # How much to advance each fold

    # Validation settings
    min_train_samples: int = 500
    min_test_samples: int = 50

    # Purging settings (to prevent look-ahead)
    purge_window: int = 10    # Bars to skip between train/test


@dataclass
class FoldResult:
    """Result from a single validation fold."""
    fold_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train_size: int
    test_size: int
    metrics: Dict[str, float]
    predictions: np.ndarray
    actuals: np.ndarray


class WalkForwardValidator:
    """
    Walk-Forward Validation framework.

    Features:
    - Time-series aware splitting (no random shuffle)
    - Expanding or rolling window support
    - Purging between train/test to prevent leakage
    - Comprehensive metrics tracking
    """

    def __init__(self, config: Optional[WalkForwardConfig] = None):
        self.config = config or WalkForwardConfig()
        self.fold_results: List[FoldResult] = []
        self.logger = logging.getLogger(__name__)

    def generate_folds(self,
                       n_samples: int,
                       expanding: bool = False) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate train/test indices for walk-forward validation.

        Args:
            n_samples: Total number of samples
            expanding: If True, use expanding window; if False, rolling window

        Returns:
            List of (train_indices, test_indices) tuples
        """
        folds = []

        # Start position for first fold
        if expanding:
            train_start = 0
        else:
            train_start = 0

        current_position = self.config.train_window

        while current_position + self.config.test_window <= n_samples:
            # Train indices
            if expanding:
                train_indices = np.arange(0, current_position)
            else:
                train_start_pos = max(0, current_position - self.config.train_window)
                train_indices = np.arange(train_start_pos, current_position)

            # Apply purge window
            train_end = current_position - self.config.purge_window

            if train_end > self.config.min_train_samples:
                train_indices = train_indices[train_indices < train_end]

            # Test indices
            test_start = current_position
            test_end = min(current_position + self.config.test_window, n_samples)
            test_indices = np.arange(test_start, test_end)

            # Validate sizes
            if len(train_indices) >= self.config.min_train_samples and \
               len(test_indices) >= self.config.min_test_samples:
                folds.append((train_indices, test_indices))

            # Move to next fold
            current_position += self.config.step_size

        self.logger.info(f"Generated {len(folds)} walk-forward folds")
        return folds

    def validate(self,
                 X: np.ndarray,
                 y: np.ndarray,
                 train_func: Callable[[np.ndarray, np.ndarray], Any],
                 predict_func: Callable[[Any, np.ndarray], np.ndarray],
                 expanding: bool = False) -> Dict[str, float]:
        """
        Run walk-forward validation.

        Args:
            X: Feature matrix
            y: Labels
            train_func: Function to train model, signature: (X_train, y_train) -> model
            predict_func: Function to predict, signature: (model, X_test) -> predictions
            expanding: Use expanding window if True

        Returns:
            Dict of aggregated metrics
        """
        self.fold_results = []
        folds = self.generate_folds(len(X), expanding)

        if not folds:
            self.logger.error("No valid folds generated")
            return {'error': 'no_valid_folds'}

        all_predictions = []
        all_actuals = []

        for i, (train_idx, test_idx) in enumerate(folds):
            self.logger.info(f"Processing fold {i+1}/{len(folds)}")

            # Split data
            X_train, y_train = X[train_idx], y[train_idx]
            X_test, y_test = X[test_idx], y[test_idx]

            try:
                # Train model
                model = train_func(X_train, y_train)

                # Predict
                predictions = predict_func(model, X_test)

                # Calculate metrics
                metrics = self._calculate_metrics(y_test, predictions)

                # Store fold result
                fold_result = FoldResult(
                    fold_index=i,
                    train_start=int(train_idx[0]),
                    train_end=int(train_idx[-1]),
                    test_start=int(test_idx[0]),
                    test_end=int(test_idx[-1]),
                    train_size=len(train_idx),
                    test_size=len(test_idx),
                    metrics=metrics,
                    predictions=predictions,
                    actuals=y_test
                )
                self.fold_results.append(fold_result)

                all_predictions.extend(predictions)
                all_actuals.extend(y_test)

                self.logger.info(f"Fold {i+1} accuracy: {metrics.get('accuracy', 0):.4f}")

            except Exception as e:
                self.logger.error(f"Fold {i+1} failed: {e}")
                continue

        # Aggregate metrics
        return self._aggregate_metrics(all_predictions, all_actuals)

    def _calculate_metrics(self,
                           y_true: np.ndarray,
                           y_pred: np.ndarray) -> Dict[str, float]:
        """Calculate classification metrics."""
        metrics = {}

        try:
            metrics['accuracy'] = accuracy_score(y_true, y_pred)
            metrics['precision_macro'] = precision_score(y_true, y_pred, average='macro', zero_division=0)
            metrics['recall_macro'] = recall_score(y_true, y_pred, average='macro', zero_division=0)
            metrics['f1_macro'] = f1_score(y_true, y_pred, average='macro', zero_division=0)

            # Per-class accuracy
            unique_classes = np.unique(np.concatenate([y_true, y_pred]))
            for cls in unique_classes:
                mask = y_true == cls
                if mask.sum() > 0:
                    metrics[f'accuracy_class_{cls}'] = (y_pred[mask] == cls).mean()

        except Exception as e:
            self.logger.error(f"Metrics calculation failed: {e}")

        return metrics

    def _aggregate_metrics(self,
                           all_predictions: List,
                           all_actuals: List) -> Dict[str, float]:
        """Aggregate metrics across all folds."""
        if not all_predictions:
            return {'error': 'no_predictions'}

        y_pred = np.array(all_predictions)
        y_true = np.array(all_actuals)

        # Overall metrics
        overall = self._calculate_metrics(y_true, y_pred)

        # Per-fold statistics
        if self.fold_results:
            fold_accuracies = [f.metrics.get('accuracy', 0) for f in self.fold_results]
            overall['mean_fold_accuracy'] = np.mean(fold_accuracies)
            overall['std_fold_accuracy'] = np.std(fold_accuracies)
            overall['min_fold_accuracy'] = np.min(fold_accuracies)
            overall['max_fold_accuracy'] = np.max(fold_accuracies)

        overall['n_folds'] = len(self.fold_results)
        overall['total_test_samples'] = len(all_predictions)

        return overall

    def get_fold_details(self) -> pd.DataFrame:
        """Get detailed results for each fold."""
        if not self.fold_results:
            return pd.DataFrame()

        rows = []
        for fold in self.fold_results:
            row = {
                'fold': fold.fold_index,
                'train_start': fold.train_start,
                'train_end': fold.train_end,
                'test_start': fold.test_start,
                'test_end': fold.test_end,
                'train_size': fold.train_size,
                'test_size': fold.test_size,
                **fold.metrics
            }
            rows.append(row)

        return pd.DataFrame(rows)

    def plot_fold_performance(self, save_path: Optional[str] = None):
        """Plot validation performance across folds."""
        try:
            import matplotlib.pyplot as plt

            if not self.fold_results:
                self.logger.warning("No fold results to plot")
                return

            df = self.get_fold_details()

            fig, axes = plt.subplots(2, 2, figsize=(12, 10))

            # Accuracy over folds
            ax = axes[0, 0]
            ax.plot(df['fold'], df['accuracy'], marker='o')
            ax.axhline(df['accuracy'].mean(), color='r', linestyle='--', label='Mean')
            ax.set_xlabel('Fold')
            ax.set_ylabel('Accuracy')
            ax.set_title('Accuracy by Fold')
            ax.legend()

            # Train/Test sizes
            ax = axes[0, 1]
            ax.bar(df['fold'] - 0.2, df['train_size'], 0.4, label='Train')
            ax.bar(df['fold'] + 0.2, df['test_size'], 0.4, label='Test')
            ax.set_xlabel('Fold')
            ax.set_ylabel('Sample Size')
            ax.set_title('Sample Sizes by Fold')
            ax.legend()

            # F1 Score
            ax = axes[1, 0]
            if 'f1_macro' in df.columns:
                ax.plot(df['fold'], df['f1_macro'], marker='s', color='green')
                ax.axhline(df['f1_macro'].mean(), color='r', linestyle='--')
            ax.set_xlabel('Fold')
            ax.set_ylabel('F1 Score (Macro)')
            ax.set_title('F1 Score by Fold')

            # Cumulative accuracy
            ax = axes[1, 1]
            cumulative_correct = 0
            cumulative_total = 0
            cum_acc = []
            for fold in self.fold_results:
                cumulative_correct += (fold.predictions == fold.actuals).sum()
                cumulative_total += len(fold.actuals)
                cum_acc.append(cumulative_correct / cumulative_total)
            ax.plot(range(len(cum_acc)), cum_acc, marker='o', color='purple')
            ax.set_xlabel('Fold')
            ax.set_ylabel('Cumulative Accuracy')
            ax.set_title('Cumulative Accuracy')

            plt.tight_layout()

            if save_path:
                plt.savefig(save_path, dpi=150)
                self.logger.info(f"Plot saved to {save_path}")
            else:
                plt.show()

        except ImportError:
            self.logger.warning("matplotlib not available for plotting")

    def analyze_stability(self) -> Dict[str, Any]:
        """Analyze model stability across folds."""
        if not self.fold_results:
            return {}

        accuracies = [f.metrics.get('accuracy', 0) for f in self.fold_results]

        # Calculate stability metrics
        stability = {
            'mean_accuracy': np.mean(accuracies),
            'std_accuracy': np.std(accuracies),
            'cv_accuracy': np.std(accuracies) / np.mean(accuracies) if np.mean(accuracies) > 0 else 0,
            'min_accuracy': np.min(accuracies),
            'max_accuracy': np.max(accuracies),
            'accuracy_range': np.max(accuracies) - np.min(accuracies)
        }

        # Check for degradation over time
        if len(accuracies) >= 3:
            first_half = np.mean(accuracies[:len(accuracies)//2])
            second_half = np.mean(accuracies[len(accuracies)//2:])
            stability['performance_drift'] = second_half - first_half

        # Consistency threshold
        stability['is_stable'] = (
            stability['cv_accuracy'] < 0.3 and
            stability['min_accuracy'] > 0.25
        )

        return stability


class TimeSeriesSplitter:
    """
    Simple time-series splitter for sklearn compatibility.
    """

    def __init__(self,
                 n_splits: int = 5,
                 test_size: int = 180,
                 gap: int = 10):
        self.n_splits = n_splits
        self.test_size = test_size
        self.gap = gap

    def split(self, X, y=None, groups=None):
        """Generate train/test indices."""
        n_samples = len(X)

        # Calculate fold positions
        total_test = self.n_splits * self.test_size
        available = n_samples - total_test - self.n_splits * self.gap

        if available < 100:
            raise ValueError("Not enough samples for requested splits")

        fold_size = available // self.n_splits

        for i in range(self.n_splits):
            train_end = fold_size * (i + 1)
            test_start = train_end + self.gap
            test_end = test_start + self.test_size

            if test_end > n_samples:
                break

            train_idx = np.arange(0, train_end)
            test_idx = np.arange(test_start, test_end)

            yield train_idx, test_idx

    def get_n_splits(self, X=None, y=None, groups=None):
        return self.n_splits
