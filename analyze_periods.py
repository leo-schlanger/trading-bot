"""
Análise por período - verificar consistência em diferentes condições de mercado.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np

from src.backtest.engine import BacktestEngine, BacktestConfig
from strategies.trend_follow import TrendFollowStrategy
from strategies.advanced_strategies import DonchianBreakoutStrategy

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
print("ANÁLISE POR PERÍODO - CONSISTÊNCIA DAS ESTRATÉGIAS")
print("=" * 80)

# Períodos a analisar
periods = [
    ("2022", "2022-01-01", "2022-12-31"),  # Bear market
    ("2023", "2023-01-01", "2023-12-31"),  # Recuperação
    ("2024", "2024-01-01", "2024-12-31"),  # Bull market
    ("2025", "2025-01-01", "2025-12-31"),  # Continuação
    ("2026", "2026-01-01", "2026-12-31"),  # Atual
    ("FULL", "2022-01-01", "2026-12-31"),  # Período completo
]

strategies_to_test = [
    ("Trend_Standard", TrendFollowStrategy(st_period=10, st_multiplier=3.0)),
    ("Donchian_55_20", DonchianBreakoutStrategy(entry_period=55, exit_period=20)),
]

for symbol in ["BTCUSDT", "SOLUSDT", "ETHUSDT"]:
    print(f"\n{'='*80}")
    print(f"ATIVO: {symbol}")
    print('='*80)

    df_full = load_data(symbol, "4h")

    # Mostrar variação do preço por período
    print(f"\nVARIAÇÃO DE PREÇO:")
    for name, start, end in periods:
        try:
            mask = (df_full.index >= start) & (df_full.index <= end)
            df_period = df_full[mask]
            if len(df_period) > 0:
                price_start = df_period['close'].iloc[0]
                price_end = df_period['close'].iloc[-1]
                change = ((price_end / price_start) - 1) * 100
                print(f"  {name}: ${price_start:.2f} -> ${price_end:.2f} ({change:+.1f}%)")
        except:
            pass

    for strat_name, strategy in strategies_to_test:
        print(f"\n--- {strat_name} ---")
        print(f"{'Período':<8} {'Trades':>7} {'WR%':>6} {'Retorno':>10} {'PF':>6} {'MaxDD':>8}")
        print("-" * 50)

        for period_name, start, end in periods:
            try:
                mask = (df_full.index >= start) & (df_full.index <= end)
                df_period = df_full[mask].copy()

                if len(df_period) < 100:  # Mínimo de dados
                    continue

                engine = BacktestEngine(config)
                results = engine.run(df_period, strategy, verbose=False)
                m = results['metrics']

                equity_start = results['equity_curve'].iloc[0]
                equity_end = results['equity_curve'].iloc[-1]
                real_return = ((equity_end - equity_start) / equity_start) * 100

                print(f"{period_name:<8} {m['total_trades']:>7} {m['win_rate']:>5.1f}% "
                      f"{real_return:>+9.1f}% {m['profit_factor']:>6.2f} "
                      f"{m['max_drawdown_pct']:>7.1f}%")

            except Exception as e:
                print(f"{period_name:<8} ERRO: {str(e)[:30]}")

print("\n" + "=" * 80)
print("LEGENDA DE PERÍODOS:")
print("  2022 = Bear Market (crash FTX, Luna)")
print("  2023 = Recuperação")
print("  2024 = Bull Market (ETFs aprovados)")
print("  2025 = Continuação")
print("  2026 = Atual (até março)")
print("=" * 80)
