"""
Script principal para executar backtests.
Compara as 3 estratégias e gera relatório.
"""

import sys
import os
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np
from datetime import datetime

from src.backtest.engine import BacktestEngine, BacktestConfig
from src.backtest.metrics import print_metrics
from strategies.ema_cross import EMACrossStrategy
from strategies.rsi_reversal import RSIReversalStrategy
from strategies.trend_follow import TrendFollowStrategy


def load_data(symbol: str = "SOLUSDT", timeframe: str = "1h") -> pd.DataFrame:
    """Carrega dados do arquivo CSV."""
    data_dir = Path(__file__).parent / "data" / "raw"
    filepath = data_dir / f"{symbol}_{timeframe}.csv"

    if not filepath.exists():
        print(f"Arquivo não encontrado: {filepath}")
        print("Execute primeiro: python scripts/download_data.py")
        return pd.DataFrame()

    df = pd.read_csv(filepath, index_col=0, parse_dates=True)
    print(f"Carregados {len(df)} candles de {df.index.min()} a {df.index.max()}")

    return df


def run_single_backtest(data: pd.DataFrame,
                         strategy,
                         config: BacktestConfig,
                         name: str,
                         verbose: bool = True) -> dict:
    """Executa backtest de uma estratégia."""
    print(f"\n{'='*60}")
    print(f"BACKTEST: {name}")
    print(f"{'='*60}")

    engine = BacktestEngine(config)
    results = engine.run(data, strategy, verbose=False)

    if verbose:
        print_metrics(results['metrics'])

    return results


def compare_strategies(data: pd.DataFrame,
                       config: BacktestConfig) -> pd.DataFrame:
    """Executa e compara todas as estratégias."""

    strategies = [
        ("EMA Crossover 9/21", EMACrossStrategy(
            fast_period=9,
            slow_period=21,
            trend_period=200,
            atr_sl_mult=2.0,
            atr_tp_mult=3.0
        )),
        ("EMA Crossover 8/21 (Scalp)", EMACrossStrategy(
            fast_period=8,
            slow_period=21,
            trend_period=100,
            atr_sl_mult=1.5,
            atr_tp_mult=2.5
        )),
        ("RSI Mean Reversion", RSIReversalStrategy(
            rsi_period=7,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            atr_sl_mult=1.5
        )),
        ("RSI Reversal (Agressivo)", RSIReversalStrategy(
            rsi_period=5,
            rsi_oversold=25,
            rsi_overbought=75,
            bb_period=15,
            atr_sl_mult=1.0
        )),
        ("Trend Following", TrendFollowStrategy(
            st_period=10,
            st_multiplier=3.0,
            atr_sl_mult=2.5,
            atr_tp_mult=4.0
        )),
        ("Trend Following (Conservador)", TrendFollowStrategy(
            st_period=14,
            st_multiplier=3.5,
            atr_sl_mult=3.0,
            atr_tp_mult=5.0,
            use_rsi_filter=True
        )),
    ]

    results_list = []

    for name, strategy in strategies:
        try:
            results = run_single_backtest(data, strategy, config, name, verbose=False)

            metrics = results['metrics']
            results_list.append({
                'Estratégia': name,
                'PnL Total ($)': f"${metrics['total_pnl']:,.2f}",
                'Retorno (%)': f"{metrics['total_pnl_pct']:.2f}%",
                'Trades': metrics['total_trades'],
                'Win Rate': f"{metrics['win_rate']:.1f}%",
                'Profit Factor': f"{metrics['profit_factor']:.2f}",
                'Sharpe': f"{metrics['sharpe_ratio']:.2f}",
                'Max DD': f"{metrics['max_drawdown_pct']:.2f}%",
                'Calmar': f"{metrics['calmar_ratio']:.2f}",
            })
        except Exception as e:
            print(f"Erro em {name}: {e}")

    comparison_df = pd.DataFrame(results_list)

    return comparison_df


def main():
    """Função principal."""
    import argparse

    parser = argparse.ArgumentParser(description="Backtest de Estratégias")
    parser.add_argument("--symbol", default="SOLUSDT", help="Par de trading")
    parser.add_argument("--timeframe", default="1h", help="Timeframe")
    parser.add_argument("--capital", type=float, default=10000, help="Capital inicial")
    parser.add_argument("--risk", type=float, default=0.02, help="Risco por trade (0.02 = 2%)")
    parser.add_argument("--strategy", default="all", help="Estratégia específica ou 'all'")
    parser.add_argument("--verbose", action="store_true", help="Mostrar detalhes")

    args = parser.parse_args()

    # Carregar dados
    data = load_data(args.symbol, args.timeframe)

    if data.empty:
        return

    # Configuração
    config = BacktestConfig(
        initial_capital=args.capital,
        risk_per_trade=args.risk,
        max_daily_loss=0.05,
        maker_fee=0.0002,
        taker_fee=0.001,
        slippage=0.0005,
        use_trailing_stop=False
    )

    print(f"\n{'#'*60}")
    print(f"CONFIGURAÇÃO DO BACKTEST")
    print(f"{'#'*60}")
    print(f"  Par: {args.symbol}")
    print(f"  Timeframe: {args.timeframe}")
    print(f"  Capital: ${args.capital:,.2f}")
    print(f"  Risco/Trade: {args.risk*100:.1f}%")
    print(f"  Período: {data.index.min().date()} a {data.index.max().date()}")
    print(f"  Total Candles: {len(data)}")

    if args.strategy == "all":
        # Comparar todas
        comparison = compare_strategies(data, config)

        print(f"\n{'='*80}")
        print("COMPARAÇÃO DE ESTRATÉGIAS")
        print('='*80)
        print(comparison.to_string(index=False))
        print('='*80)

        # Salvar resultados
        results_dir = Path(__file__).parent / "results"
        results_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = results_dir / f"comparison_{args.symbol}_{args.timeframe}_{timestamp}.csv"
        comparison.to_csv(filepath, index=False)
        print(f"\nResultados salvos em: {filepath}")

    else:
        # Executar estratégia específica
        strategy_map = {
            "ema": EMACrossStrategy(),
            "rsi": RSIReversalStrategy(),
            "trend": TrendFollowStrategy(),
        }

        if args.strategy.lower() in strategy_map:
            strategy = strategy_map[args.strategy.lower()]
            results = run_single_backtest(
                data, strategy, config,
                args.strategy.upper(),
                verbose=True
            )
        else:
            print(f"Estratégia '{args.strategy}' não encontrada.")
            print(f"Opções: {list(strategy_map.keys())} ou 'all'")


if __name__ == "__main__":
    main()
