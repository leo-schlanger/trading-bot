"""
Backtest das estratégias avançadas baseadas em pesquisa.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np
from datetime import datetime

from src.backtest.engine import BacktestEngine, BacktestConfig
from src.backtest.metrics import print_metrics

from strategies.advanced_strategies import (
    HullMACrossStrategy,
    KeltnerSqueezeStrategy,
    WilliamsRSIStrategy,
    DonchianBreakoutStrategy,
    MomentumBreakoutStrategy
)


def load_data(symbol: str = "SOLUSDT", timeframe: str = "4h") -> pd.DataFrame:
    """Carrega dados."""
    data_dir = Path(__file__).parent / "data" / "raw"
    filepath = data_dir / f"{symbol}_{timeframe}.csv"

    if not filepath.exists():
        print(f"Arquivo não encontrado: {filepath}")
        return pd.DataFrame()

    df = pd.read_csv(filepath, index_col=0, parse_dates=True)
    return df


def run_advanced_backtest():
    """Executa backtest das estratégias avançadas."""

    config = BacktestConfig(
        initial_capital=10000,
        risk_per_trade=0.02,
        max_daily_loss=0.05,
        maker_fee=0.0002,
        taker_fee=0.001,
        slippage=0.0005
    )

    # Estratégias avançadas
    strategies = [
        # Hull MA variations
        ("Hull_9_21", HullMACrossStrategy(
            fast_period=9, slow_period=21,
            atr_sl_mult=2.0, atr_tp_mult=3.0
        )),
        ("Hull_14_28", HullMACrossStrategy(
            fast_period=14, slow_period=28,
            atr_sl_mult=2.5, atr_tp_mult=4.0
        )),
        ("Hull_21_55", HullMACrossStrategy(
            fast_period=21, slow_period=55,
            atr_sl_mult=3.0, atr_tp_mult=5.0
        )),

        # Keltner Squeeze
        ("Squeeze_Standard", KeltnerSqueezeStrategy(
            bb_period=20, bb_std=2.0,
            kc_period=20, kc_mult=1.5,
            squeeze_lookback=6
        )),
        ("Squeeze_Tight", KeltnerSqueezeStrategy(
            bb_period=15, bb_std=1.5,
            kc_period=15, kc_mult=1.0,
            squeeze_lookback=4
        )),
        ("Squeeze_Wide", KeltnerSqueezeStrategy(
            bb_period=25, bb_std=2.5,
            kc_period=25, kc_mult=2.0,
            squeeze_lookback=8
        )),

        # Williams %R + RSI
        ("WilliamsRSI_14", WilliamsRSIStrategy(
            williams_period=14, rsi_period=14,
            atr_sl_mult=1.5, atr_tp_mult=2.0
        )),
        ("WilliamsRSI_7", WilliamsRSIStrategy(
            williams_period=7, rsi_period=7,
            atr_sl_mult=1.0, atr_tp_mult=1.5
        )),
        ("WilliamsRSI_21", WilliamsRSIStrategy(
            williams_period=21, rsi_period=21,
            atr_sl_mult=2.0, atr_tp_mult=2.5
        )),

        # Donchian Breakout
        ("Donchian_20_10", DonchianBreakoutStrategy(
            entry_period=20, exit_period=10,
            atr_sl_mult=2.0
        )),
        ("Donchian_55_20", DonchianBreakoutStrategy(
            entry_period=55, exit_period=20,
            atr_sl_mult=2.5
        )),
        ("Donchian_10_5", DonchianBreakoutStrategy(
            entry_period=10, exit_period=5,
            atr_sl_mult=1.5
        )),

        # Momentum Breakout
        ("Momentum_Standard", MomentumBreakoutStrategy(
            momentum_period=14, volume_threshold=1.5,
            atr_sl_mult=2.0, atr_tp_mult=3.5
        )),
        ("Momentum_Fast", MomentumBreakoutStrategy(
            momentum_period=7, volume_threshold=1.3,
            atr_sl_mult=1.5, atr_tp_mult=2.5
        )),
        ("Momentum_Slow", MomentumBreakoutStrategy(
            momentum_period=21, volume_threshold=2.0,
            atr_sl_mult=2.5, atr_tp_mult=4.0
        )),
    ]

    symbols = ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
    timeframes = ["4h"]  # Focar no 4h que mostrou melhores resultados

    all_results = []

    print("=" * 100)
    print("BACKTEST ESTRATÉGIAS AVANÇADAS")
    print(f"Capital: $10,000 | Risco: 2% | Período: 2022-2026")
    print("=" * 100)

    for symbol in symbols:
        for tf in timeframes:
            data = load_data(symbol, tf)
            if data.empty:
                continue

            print(f"\n[{symbol} {tf}] {len(data)} candles")
            print("-" * 80)

            for name, strategy in strategies:
                try:
                    engine = BacktestEngine(config)
                    results = engine.run(data.copy(), strategy, verbose=False)
                    m = results['metrics']

                    all_results.append({
                        'Ativo': symbol.replace('USDT', ''),
                        'TF': tf,
                        'Estratégia': name,
                        'Retorno %': round(m['total_pnl_pct'], 1),
                        'Trades': m['total_trades'],
                        'Win Rate %': round(m['win_rate'], 1),
                        'Avg Win %': round(m['avg_win_pct'], 2),
                        'Avg Loss %': round(m['avg_loss_pct'], 2),
                        'R/R': round(m['risk_reward_ratio'], 2),
                        'PF': round(m['profit_factor'], 2),
                        'Sharpe': round(m['sharpe_ratio'], 3),
                        'Max DD %': round(m['max_drawdown_pct'], 1),
                        'Expectancy $': round(m['expectancy'], 2),
                    })

                    status = "+" if m['total_pnl'] > 0 else "-"
                    print(f"  {name:20} | {status}{abs(m['total_pnl_pct']):6.1f}% | "
                          f"WR:{m['win_rate']:4.0f}% | R/R:{m['risk_reward_ratio']:4.2f} | "
                          f"PF:{m['profit_factor']:4.2f} | Trades:{m['total_trades']:4}")

                except Exception as e:
                    print(f"  {name:20} | ERRO: {str(e)[:50]}")

    # Criar DataFrame e ordenar
    df = pd.DataFrame(all_results)
    df = df.sort_values('Retorno %', ascending=False)

    # Salvar
    results_dir = Path(__file__).parent / "results"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = results_dir / f"advanced_backtest_{timestamp}.csv"
    df.to_csv(csv_path, index=False)

    # Imprimir resumo
    print("\n" + "=" * 100)
    print("TOP 15 ESTRATÉGIAS AVANÇADAS")
    print("=" * 100)
    print(f"\n{'Ativo':<6} {'TF':<4} {'Estratégia':<22} {'Ret%':>8} {'WR%':>6} "
          f"{'AvgWin%':>8} {'AvgLoss%':>9} {'R/R':>5} {'PF':>5} {'Sharpe':>7} {'DD%':>7}")
    print("-" * 100)

    for _, row in df.head(15).iterrows():
        print(f"{row['Ativo']:<6} {row['TF']:<4} {row['Estratégia']:<22} "
              f"{row['Retorno %']:>+7.1f}% {row['Win Rate %']:>5.0f}% "
              f"{row['Avg Win %']:>+7.2f}% {row['Avg Loss %']:>+8.2f}% "
              f"{row['R/R']:>5.2f} {row['PF']:>5.2f} {row['Sharpe']:>7.3f} "
              f"{row['Max DD %']:>6.1f}%")

    # Análise por tipo
    print("\n" + "=" * 100)
    print("ANÁLISE POR TIPO DE ESTRATÉGIA")
    print("=" * 100)

    types = {
        'Hull MA': df[df['Estratégia'].str.startswith('Hull')],
        'Keltner Squeeze': df[df['Estratégia'].str.startswith('Squeeze')],
        'Williams %R': df[df['Estratégia'].str.startswith('Williams')],
        'Donchian': df[df['Estratégia'].str.startswith('Donchian')],
        'Momentum': df[df['Estratégia'].str.startswith('Momentum')],
    }

    for name, tdf in types.items():
        if tdf.empty:
            continue
        profitable = len(tdf[tdf['Retorno %'] > 0])
        print(f"\n{name}:")
        print(f"  Lucrativas: {profitable}/{len(tdf)}")
        print(f"  Retorno Médio: {tdf['Retorno %'].mean():+.1f}%")
        print(f"  Win Rate Médio: {tdf['Win Rate %'].mean():.1f}%")
        print(f"  Avg Win: {tdf['Avg Win %'].mean():.2f}% | Avg Loss: {tdf['Avg Loss %'].mean():.2f}%")
        print(f"  R/R Médio: {tdf['R/R'].mean():.2f}")
        print(f"  PF Médio: {tdf['PF'].mean():.2f}")
        best = tdf.iloc[0]
        print(f"  Melhor: {best['Ativo']} {best['Estratégia']} ({best['Retorno %']:+.1f}%)")

    print(f"\n\nResultados salvos em: {csv_path}")

    return df


if __name__ == "__main__":
    run_advanced_backtest()
