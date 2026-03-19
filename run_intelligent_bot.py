"""
Main script to run the Intelligent Trading Bot.

Usage:
    python run_intelligent_bot.py --data data/btc_4h.csv --mode backtest
    python run_intelligent_bot.py --data data/btc_4h.csv --mode paper
    python run_intelligent_bot.py --config config/bot_config.yaml --mode live
"""

import argparse
import logging
from pathlib import Path
from datetime import datetime
import yaml
import pandas as pd
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.bot.intelligent_engine import IntelligentEngine, IntelligentConfig
from src.ml.strategy_selector import StrategyType
from src.backtest.engine import BaseStrategy
from src.indicators.technical import (
    ema, rsi, atr, supertrend, macd, bollinger_bands, sma
)


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# Strategy Implementations
# ============================================================

class EMACrossStrategy(BaseStrategy):
    """EMA Crossover Strategy."""
    warmup_period = 60

    def __init__(self, fast=9, slow=21, trend=50, stop_atr=2.0, tp_atr=3.0):
        self.fast = fast
        self.slow = slow
        self.trend = trend
        self.stop_atr_mult = stop_atr
        self.tp_atr_mult = tp_atr

    def setup(self, data: pd.DataFrame):
        self.ema_fast = ema(data['close'], self.fast)
        self.ema_slow = ema(data['close'], self.slow)
        self.ema_trend = ema(data['close'], self.trend)
        self.atr_val = atr(data['high'], data['low'], data['close'], 14)
        self.rsi_val = rsi(data['close'], 14)

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        if index < self.warmup_period:
            return 0

        fast = self.ema_fast.iloc[index]
        slow = self.ema_slow.iloc[index]
        trend = self.ema_trend.iloc[index]
        rsi_v = self.rsi_val.iloc[index]
        close = data.iloc[index]['close']

        prev_fast = self.ema_fast.iloc[index - 1]
        prev_slow = self.ema_slow.iloc[index - 1]

        # Bullish cross above trend
        if prev_fast <= prev_slow and fast > slow:
            if close > trend and rsi_v < 70:
                return 1

        # Bearish cross below trend
        if prev_fast >= prev_slow and fast < slow:
            if close < trend and rsi_v > 30:
                return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> float:
        atr_v = self.atr_val.iloc[index]
        close = data.iloc[index]['close']

        if signal > 0:
            return close - (atr_v * self.stop_atr_mult)
        else:
            return close + (atr_v * self.stop_atr_mult)

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> float:
        atr_v = self.atr_val.iloc[index]
        close = data.iloc[index]['close']

        if signal > 0:
            return close + (atr_v * self.tp_atr_mult)
        else:
            return close - (atr_v * self.tp_atr_mult)


class TrendFollowStrategy(BaseStrategy):
    """Trend Following with Supertrend."""
    warmup_period = 120

    def __init__(self, st_period=10, st_mult=3.0, trend_period=100,
                 stop_atr=2.5, tp_atr=4.0):
        self.st_period = st_period
        self.st_mult = st_mult
        self.trend_period = trend_period
        self.stop_atr_mult = stop_atr
        self.tp_atr_mult = tp_atr

    def setup(self, data: pd.DataFrame):
        self.supertrend_line, self.supertrend_dir = supertrend(
            data['high'], data['low'], data['close'],
            self.st_period, self.st_mult
        )
        self.ema_trend = ema(data['close'], self.trend_period)
        self.macd_line, self.macd_signal, self.macd_hist = macd(data['close'])
        self.atr_val = atr(data['high'], data['low'], data['close'], 14)

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        if index < self.warmup_period:
            return 0

        direction = self.supertrend_dir.iloc[index]
        prev_direction = self.supertrend_dir.iloc[index - 1]
        close = data.iloc[index]['close']
        trend = self.ema_trend.iloc[index]
        macd_h = self.macd_hist.iloc[index]

        # Trend change with confirmation
        if prev_direction == -1 and direction == 1:
            if close > trend and macd_h > 0:
                return 1

        if prev_direction == 1 and direction == -1:
            if close < trend and macd_h < 0:
                return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> float:
        atr_v = self.atr_val.iloc[index]
        close = data.iloc[index]['close']

        if signal > 0:
            return close - (atr_v * self.stop_atr_mult)
        else:
            return close + (atr_v * self.stop_atr_mult)

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> float:
        atr_v = self.atr_val.iloc[index]
        close = data.iloc[index]['close']

        if signal > 0:
            return close + (atr_v * self.tp_atr_mult)
        else:
            return close - (atr_v * self.tp_atr_mult)


class RSIReversalStrategy(BaseStrategy):
    """RSI Mean Reversion Strategy."""
    warmup_period = 50

    def __init__(self, rsi_period=14, oversold=30, overbought=70,
                 bb_period=20, stop_atr=1.5, tp_atr=2.5):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.bb_period = bb_period
        self.stop_atr_mult = stop_atr
        self.tp_atr_mult = tp_atr

    def setup(self, data: pd.DataFrame):
        self.rsi_val = rsi(data['close'], self.rsi_period)
        self.bb_upper, self.bb_mid, self.bb_lower = bollinger_bands(
            data['close'], self.bb_period
        )
        self.ema_trend = ema(data['close'], 100)
        self.atr_val = atr(data['high'], data['low'], data['close'], 14)

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        if index < self.warmup_period:
            return 0

        rsi_v = self.rsi_val.iloc[index]
        close = data.iloc[index]['close']
        bb_lower = self.bb_lower.iloc[index]
        bb_upper = self.bb_upper.iloc[index]
        trend = self.ema_trend.iloc[index]

        # Oversold + at lower BB + above trend
        if rsi_v < self.oversold and close <= bb_lower and close > trend:
            return 1

        # Overbought + at upper BB + below trend
        if rsi_v > self.overbought and close >= bb_upper and close < trend:
            return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> float:
        atr_v = self.atr_val.iloc[index]
        close = data.iloc[index]['close']

        if signal > 0:
            return close - (atr_v * self.stop_atr_mult)
        else:
            return close + (atr_v * self.stop_atr_mult)

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> float:
        atr_v = self.atr_val.iloc[index]
        close = data.iloc[index]['close']

        if signal > 0:
            return close + (atr_v * self.tp_atr_mult)
        else:
            return close - (atr_v * self.tp_atr_mult)


class MomentumStrategy(BaseStrategy):
    """Momentum-based Strategy."""
    warmup_period = 50

    def __init__(self, fast=10, slow=20, rsi_period=14,
                 stop_atr=2.0, tp_atr=3.0):
        self.fast = fast
        self.slow = slow
        self.rsi_period = rsi_period
        self.stop_atr_mult = stop_atr
        self.tp_atr_mult = tp_atr

    def setup(self, data: pd.DataFrame):
        self.momentum_fast = data['close'].diff(self.fast)
        self.momentum_slow = data['close'].diff(self.slow)
        self.rsi_val = rsi(data['close'], self.rsi_period)
        self.ema_trend = ema(data['close'], 50)
        self.atr_val = atr(data['high'], data['low'], data['close'], 14)

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        if index < self.warmup_period:
            return 0

        mom_fast = self.momentum_fast.iloc[index]
        mom_slow = self.momentum_slow.iloc[index]
        rsi_v = self.rsi_val.iloc[index]
        close = data.iloc[index]['close']
        trend = self.ema_trend.iloc[index]

        # Strong upward momentum
        if mom_fast > 0 and mom_slow > 0:
            if close > trend and rsi_v > 50 and rsi_v < 75:
                return 1

        # Strong downward momentum
        if mom_fast < 0 and mom_slow < 0:
            if close < trend and rsi_v < 50 and rsi_v > 25:
                return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> float:
        atr_v = self.atr_val.iloc[index]
        close = data.iloc[index]['close']

        if signal > 0:
            return close - (atr_v * self.stop_atr_mult)
        else:
            return close + (atr_v * self.stop_atr_mult)

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> float:
        atr_v = self.atr_val.iloc[index]
        close = data.iloc[index]['close']

        if signal > 0:
            return close + (atr_v * self.tp_atr_mult)
        else:
            return close - (atr_v * self.tp_atr_mult)


# ============================================================
# Main Functions
# ============================================================

def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_data(data_path: str) -> pd.DataFrame:
    """Load OHLCV data from CSV."""
    df = pd.read_csv(data_path, index_col=0, parse_dates=True)
    df = df.sort_index()
    logger.info(f"Loaded {len(df)} bars from {data_path}")
    return df


def create_engine(config: dict) -> IntelligentEngine:
    """Create and configure the intelligent engine."""
    engine_config = IntelligentConfig(
        initial_capital=config.get('general', {}).get('initial_capital', 500.0),
        maker_fee=config.get('exchange', {}).get('maker_fee', 0.0002),
        taker_fee=config.get('exchange', {}).get('taker_fee', 0.001),
        slippage=config.get('exchange', {}).get('slippage', 0.0005),
        use_ml_strategy_selection=config.get('ml', {}).get('strategy', {}).get('use_ml_selection', True),
        min_strategy_confidence=config.get('ml', {}).get('strategy', {}).get('min_confidence', 0.3),
        enable_circuit_breakers=config.get('safety', {}).get('enabled', True),
        max_consecutive_losses=config.get('safety', {}).get('max_consecutive_losses', 3),
        max_daily_loss_pct=config.get('safety', {}).get('max_daily_loss_pct', 0.05),
        max_drawdown_pct=config.get('safety', {}).get('max_drawdown_pct', 0.20),
        use_trailing_stop=config.get('trailing_stop', {}).get('enabled', True),
        trailing_stop_atr_mult=config.get('trailing_stop', {}).get('atr_multiplier', 2.0)
    )

    engine = IntelligentEngine(engine_config)

    # Register strategies
    strat_config = config.get('strategies', {})

    ema_conf = strat_config.get('ema_cross', {})
    engine.register_strategy(
        StrategyType.EMA_CROSS,
        EMACrossStrategy(
            fast=ema_conf.get('fast_period', 9),
            slow=ema_conf.get('slow_period', 21),
            trend=ema_conf.get('trend_period', 50),
            stop_atr=ema_conf.get('stop_atr', 2.0),
            tp_atr=ema_conf.get('tp_atr', 3.0)
        )
    )

    tf_conf = strat_config.get('trend_follow', {})
    engine.register_strategy(
        StrategyType.TREND_FOLLOW,
        TrendFollowStrategy(
            st_period=tf_conf.get('supertrend_period', 10),
            st_mult=tf_conf.get('supertrend_mult', 3.0),
            trend_period=tf_conf.get('trend_period', 100),
            stop_atr=tf_conf.get('stop_atr', 2.5),
            tp_atr=tf_conf.get('tp_atr', 4.0)
        )
    )

    rsi_conf = strat_config.get('rsi_reversal', {})
    engine.register_strategy(
        StrategyType.RSI_REVERSAL,
        RSIReversalStrategy(
            rsi_period=rsi_conf.get('rsi_period', 14),
            oversold=rsi_conf.get('oversold', 30),
            overbought=rsi_conf.get('overbought', 70),
            bb_period=rsi_conf.get('bb_period', 20),
            stop_atr=rsi_conf.get('stop_atr', 1.5),
            tp_atr=rsi_conf.get('tp_atr', 2.5)
        )
    )

    mom_conf = strat_config.get('momentum', {})
    engine.register_strategy(
        StrategyType.MOMENTUM,
        MomentumStrategy(
            fast=mom_conf.get('fast_period', 10),
            slow=mom_conf.get('slow_period', 20),
            rsi_period=mom_conf.get('rsi_period', 14),
            stop_atr=mom_conf.get('stop_atr', 2.0),
            tp_atr=mom_conf.get('tp_atr', 3.0)
        )
    )

    return engine


def print_results(results: dict):
    """Print backtest results."""
    metrics = results['metrics']

    print("\n" + "="*60)
    print("INTELLIGENT BOT BACKTEST RESULTS")
    print("="*60)

    print(f"\nCapital: ${metrics.get('initial_capital', 500):.2f} -> ${metrics.get('final_capital', 0):.2f}")
    print(f"Total Return: {metrics.get('total_return_pct', 0):.2f}%")
    print(f"Total PnL: ${metrics.get('total_pnl', 0):.2f}")

    print(f"\nTotal Trades: {metrics.get('total_trades', 0)}")
    print(f"Win Rate: {metrics.get('win_rate', 0)*100:.1f}%")
    print(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")

    print(f"\nSharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"Sortino Ratio: {metrics.get('sortino_ratio', 0):.2f}")
    print(f"Calmar Ratio: {metrics.get('calmar_ratio', 0):.2f}")

    print(f"\nMax Drawdown: {metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"Max Drawdown Duration: {metrics.get('max_drawdown_duration_days', 0):.1f} days")

    print(f"\nAvg Win: ${metrics.get('avg_win', 0):.2f}")
    print(f"Avg Loss: ${metrics.get('avg_loss', 0):.2f}")
    print(f"Best Trade: ${metrics.get('best_trade', 0):.2f}")
    print(f"Worst Trade: ${metrics.get('worst_trade', 0):.2f}")

    print(f"\nConsecutive Wins (Max): {metrics.get('max_consecutive_wins', 0)}")
    print(f"Consecutive Losses (Max): {metrics.get('max_consecutive_losses', 0)}")

    # Regime distribution
    if 'regime_history' in results:
        from collections import Counter
        regimes = Counter(results['regime_history'])
        print("\nRegime Distribution:")
        for regime, count in regimes.most_common():
            pct = count / len(results['regime_history']) * 100
            print(f"  {regime}: {pct:.1f}%")

    print("\n" + "="*60)


def run_backtest(data: pd.DataFrame, config: dict, verbose: bool = True):
    """Run backtest with the intelligent engine."""
    engine = create_engine(config)

    logger.info("Starting backtest...")
    results = engine.run(data, verbose=verbose)

    print_results(results)

    # Save results
    results_dir = Path(config.get('backtest', {}).get('results_dir', 'results'))
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Save equity curve
    results['equity_curve'].to_csv(results_dir / f'equity_{timestamp}.csv')

    # Save trades
    if results['trades']:
        trades_df = pd.DataFrame([
            {
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'side': t.side.name,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'size': t.size,
                'pnl': t.pnl,
                'pnl_pct': t.pnl_pct,
                'fees': t.fees,
                'exit_reason': t.exit_reason
            }
            for t in results['trades']
        ])
        trades_df.to_csv(results_dir / f'trades_{timestamp}.csv', index=False)

    # Save decision log
    if results['decision_log']:
        pd.DataFrame(results['decision_log']).to_csv(
            results_dir / f'decisions_{timestamp}.csv', index=False
        )

    logger.info(f"Results saved to {results_dir}")

    return results


def main():
    parser = argparse.ArgumentParser(description='Run Intelligent Trading Bot')
    parser.add_argument('--data', required=True, help='Path to OHLCV data CSV')
    parser.add_argument('--config', default='config/bot_config.yaml', help='Path to config file')
    parser.add_argument('--mode', choices=['backtest', 'paper', 'live'], default='backtest')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Load config
    config_path = Path(args.config)
    if config_path.exists():
        config = load_config(str(config_path))
        logger.info(f"Loaded config from {config_path}")
    else:
        logger.warning(f"Config not found at {config_path}, using defaults")
        config = {}

    # Load data
    data = load_data(args.data)

    if args.mode == 'backtest':
        run_backtest(data, config, args.verbose)
    elif args.mode == 'paper':
        logger.info("Paper trading mode not implemented yet")
        # TODO: Implement paper trading
    elif args.mode == 'live':
        logger.info("Live trading mode not implemented yet")
        # TODO: Implement live trading


if __name__ == '__main__':
    main()
