"""
Validação detalhada - verificar cálculos.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np

from src.backtest.engine import BacktestEngine, BacktestConfig
from strategies.ema_cross import EMACrossStrategy
from strategies.trend_follow import TrendFollowStrategy
from strategies.advanced_strategies import DonchianBreakoutStrategy, MomentumBreakoutStrategy

def load_data(symbol, tf):
    path = Path(__file__).parent / "data" / "raw" / f"{symbol}_{tf}.csv"
    return pd.read_csv(path, index_col=0, parse_dates=True)

config = BacktestConfig(
    initial_capital=10000,
    risk_per_trade=0.02,
    maker_fee=0.0002,
    taker_fee=0.001,
    slippage=0.0005
)

print("=" * 80)
print("VALIDAÇÃO DETALHADA DOS BACKTESTS")
print("=" * 80)

# Testar todas as combinações principais
tests = [
    ("SOLUSDT", "4h", "Trend_Standard", TrendFollowStrategy(st_period=10, st_multiplier=3.0)),
    ("BTCUSDT", "4h", "Trend_Standard", TrendFollowStrategy(st_period=10, st_multiplier=3.0)),
    ("SOLUSDT", "4h", "Donchian_20_10", DonchianBreakoutStrategy(entry_period=20, exit_period=10)),
    ("BTCUSDT", "4h", "Donchian_55_20", DonchianBreakoutStrategy(entry_period=55, exit_period=20)),
    ("ETHUSDT", "4h", "Momentum_Standard", MomentumBreakoutStrategy()),
    ("SOLUSDT", "4h", "EMA_9_21", EMACrossStrategy(fast_period=9, slow_period=21)),
]

results = []

for symbol, tf, name, strategy in tests:
    try:
        df = load_data(symbol, tf)
        engine = BacktestEngine(config)
        r = engine.run(df.copy(), strategy, verbose=False)
        m = r['metrics']

        # Calcular retorno real
        equity_start = r['equity_curve'].iloc[0]
        equity_end = r['equity_curve'].iloc[-1]
        real_return = ((equity_end - equity_start) / equity_start) * 100

        # Soma dos PnLs dos trades
        pnl_sum = sum(t.pnl for t in r['trades'])

        print(f"\n{symbol} {tf} | {name}")
        print(f"  Trades: {m['total_trades']}")
        print(f"  Win Rate: {m['win_rate']:.1f}%")
        print(f"  Equity: ${equity_start:.2f} -> ${equity_end:.2f}")
        print(f"  Retorno Real: {real_return:+.2f}%")
        print(f"  Soma PnL trades: ${pnl_sum:.2f}")
        print(f"  Profit Factor: {m['profit_factor']:.2f}")
        print(f"  Max DD: {m['max_drawdown_pct']:.1f}%")

        # Verificar se há trades
        if r['trades']:
            wins = [t for t in r['trades'] if t.pnl > 0]
            losses = [t for t in r['trades'] if t.pnl < 0]
            print(f"  Wins: {len(wins)} | Losses: {len(losses)}")
            if wins:
                print(f"  Avg Win: ${np.mean([t.pnl for t in wins]):.2f}")
            if losses:
                print(f"  Avg Loss: ${np.mean([t.pnl for t in losses]):.2f}")

        results.append({
            'Symbol': symbol,
            'TF': tf,
            'Strategy': name,
            'Trades': m['total_trades'],
            'Win Rate': m['win_rate'],
            'Return %': real_return,
            'PF': m['profit_factor'],
            'Max DD %': m['max_drawdown_pct']
        })

    except Exception as e:
        print(f"\n{symbol} {tf} | {name} - ERRO: {e}")

print("\n" + "=" * 80)
print("RESUMO")
print("=" * 80)

df_results = pd.DataFrame(results)
df_results = df_results.sort_values('Return %', ascending=False)

print(f"\n{'Symbol':<10} {'TF':<4} {'Strategy':<20} {'Return':>10} {'WR':>8} {'PF':>6} {'DD':>8}")
print("-" * 70)
for _, row in df_results.iterrows():
    print(f"{row['Symbol']:<10} {row['TF']:<4} {row['Strategy']:<20} "
          f"{row['Return %']:>+9.1f}% {row['Win Rate']:>7.1f}% "
          f"{row['PF']:>6.2f} {row['Max DD %']:>7.1f}%")

# Contar lucrativas
profitable = len(df_results[df_results['Return %'] > 0])
print(f"\nEstratégias lucrativas: {profitable}/{len(df_results)}")
