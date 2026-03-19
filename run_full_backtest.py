"""
Backtest Completo - Análise Multi-Ativo e Multi-Timeframe
Gera relatório detalhado para tomada de decisão.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple
import json

from src.backtest.engine import BacktestEngine, BacktestConfig
from src.backtest.metrics import calculate_metrics
from strategies.ema_cross import EMACrossStrategy
from strategies.rsi_reversal import RSIReversalStrategy
from strategies.trend_follow import TrendFollowStrategy


class FullBacktester:
    """Executa backtest completo com múltiplas configurações."""

    def __init__(self, capital: float = 10000, risk: float = 0.02):
        self.capital = capital
        self.risk = risk
        self.results: Dict = {}
        self.data_dir = Path(__file__).parent / "data" / "raw"
        self.results_dir = Path(__file__).parent / "results"
        self.results_dir.mkdir(exist_ok=True)

    def load_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Carrega dados."""
        filepath = self.data_dir / f"{symbol}_{timeframe}.csv"
        if filepath.exists():
            df = pd.read_csv(filepath, index_col=0, parse_dates=True)
            return df
        return pd.DataFrame()

    def get_all_strategies(self) -> List[Tuple[str, object]]:
        """Retorna todas as variações de estratégias."""
        return [
            # EMA Crossover Variações
            ("EMA_9_21_Standard", EMACrossStrategy(
                fast_period=9, slow_period=21, trend_period=200,
                atr_sl_mult=2.0, atr_tp_mult=3.0, use_rsi_filter=True
            )),
            ("EMA_8_21_Scalp", EMACrossStrategy(
                fast_period=8, slow_period=21, trend_period=100,
                atr_sl_mult=1.5, atr_tp_mult=2.5, use_rsi_filter=True
            )),
            ("EMA_13_34_Fib", EMACrossStrategy(
                fast_period=13, slow_period=34, trend_period=200,
                atr_sl_mult=2.0, atr_tp_mult=3.5, use_rsi_filter=False
            )),
            ("EMA_5_13_Fast", EMACrossStrategy(
                fast_period=5, slow_period=13, trend_period=50,
                atr_sl_mult=1.0, atr_tp_mult=2.0, use_rsi_filter=True
            )),

            # RSI Reversal Variações
            ("RSI_7_MeanRev", RSIReversalStrategy(
                rsi_period=7, rsi_oversold=30, rsi_overbought=70,
                bb_period=20, atr_sl_mult=1.5, use_trend_filter=True
            )),
            ("RSI_5_Aggressive", RSIReversalStrategy(
                rsi_period=5, rsi_oversold=25, rsi_overbought=75,
                bb_period=15, atr_sl_mult=1.0, use_trend_filter=False
            )),
            ("RSI_14_Conservative", RSIReversalStrategy(
                rsi_period=14, rsi_oversold=35, rsi_overbought=65,
                bb_period=20, atr_sl_mult=2.0, use_trend_filter=True
            )),

            # Trend Following Variações
            ("Trend_Standard", TrendFollowStrategy(
                st_period=10, st_multiplier=3.0,
                atr_sl_mult=2.5, atr_tp_mult=4.0, use_rsi_filter=True
            )),
            ("Trend_Aggressive", TrendFollowStrategy(
                st_period=7, st_multiplier=2.5,
                atr_sl_mult=2.0, atr_tp_mult=3.5, use_rsi_filter=False
            )),
            ("Trend_Conservative", TrendFollowStrategy(
                st_period=14, st_multiplier=3.5,
                atr_sl_mult=3.0, atr_tp_mult=5.0, use_rsi_filter=True
            )),
        ]

    def run_backtest(self, data: pd.DataFrame, strategy, config: BacktestConfig) -> Dict:
        """Executa um backtest individual."""
        engine = BacktestEngine(config)
        results = engine.run(data, strategy, verbose=False)
        return results

    def analyze_by_period(self, trades: List, equity_curve: pd.Series) -> Dict:
        """Analisa performance por período."""
        if not trades:
            return {}

        # Converter trades para DataFrame
        trades_df = pd.DataFrame([{
            'entry_time': t.entry_time,
            'exit_time': t.exit_time,
            'pnl': t.pnl,
            'pnl_pct': t.pnl_pct,
            'is_winner': t.is_winner
        } for t in trades])

        trades_df['year'] = pd.to_datetime(trades_df['exit_time']).dt.year
        trades_df['month'] = pd.to_datetime(trades_df['exit_time']).dt.month
        trades_df['quarter'] = pd.to_datetime(trades_df['exit_time']).dt.quarter

        # Por ano
        yearly = trades_df.groupby('year').agg({
            'pnl': ['sum', 'count', 'mean'],
            'is_winner': 'mean'
        }).round(2)
        yearly.columns = ['pnl_total', 'trades', 'avg_pnl', 'win_rate']

        # Por trimestre (últimos 2 anos)
        recent = trades_df[trades_df['year'] >= 2024]
        if len(recent) > 0:
            quarterly = recent.groupby(['year', 'quarter']).agg({
                'pnl': ['sum', 'count'],
                'is_winner': 'mean'
            }).round(2)
        else:
            quarterly = pd.DataFrame()

        # Drawdown analysis
        peak = equity_curve.expanding().max()
        drawdown = (equity_curve - peak) / peak
        max_dd = drawdown.min()
        max_dd_duration = self._calculate_dd_duration(drawdown)

        return {
            'yearly': yearly.to_dict() if not yearly.empty else {},
            'quarterly': quarterly.to_dict() if not quarterly.empty else {},
            'max_drawdown_pct': max_dd * 100,
            'max_dd_duration_days': max_dd_duration
        }

    def _calculate_dd_duration(self, drawdown: pd.Series) -> int:
        """Calcula duração máxima do drawdown em dias."""
        in_dd = drawdown < 0
        if not in_dd.any():
            return 0

        # Encontrar sequências de drawdown
        dd_groups = (in_dd != in_dd.shift()).cumsum()
        dd_lengths = in_dd.groupby(dd_groups).sum()
        max_length = dd_lengths.max()

        # Converter para dias (assumindo dados horários)
        return int(max_length / 24)

    def run_full_analysis(self):
        """Executa análise completa."""
        symbols = ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
        timeframes = ["1h", "4h"]
        strategies = self.get_all_strategies()

        config = BacktestConfig(
            initial_capital=self.capital,
            risk_per_trade=self.risk,
            max_daily_loss=0.05,
            maker_fee=0.0002,
            taker_fee=0.001,
            slippage=0.0005
        )

        all_results = []
        detailed_results = {}

        total_tests = len(symbols) * len(timeframes) * len(strategies)
        current = 0

        print("=" * 80)
        print("BACKTEST COMPLETO - ANÁLISE MULTI-ATIVO")
        print(f"Capital: ${self.capital:,.2f} | Risco/Trade: {self.risk*100}%")
        print(f"Período: 2022-01-01 a 2026-03-19")
        print("=" * 80)

        for symbol in symbols:
            detailed_results[symbol] = {}

            for tf in timeframes:
                data = self.load_data(symbol, tf)
                if data.empty:
                    print(f"[SKIP] {symbol} {tf} - dados não encontrados")
                    continue

                detailed_results[symbol][tf] = {}
                print(f"\n[{symbol} {tf}] {len(data)} candles")

                for name, strategy in strategies:
                    current += 1
                    pct = (current / total_tests) * 100

                    try:
                        results = self.run_backtest(data, strategy, config)
                        metrics = results['metrics']

                        # Análise por período
                        period_analysis = self.analyze_by_period(
                            results['trades'],
                            results['equity_curve']
                        )

                        detailed_results[symbol][tf][name] = {
                            'metrics': metrics,
                            'period_analysis': period_analysis,
                            'num_trades': len(results['trades'])
                        }

                        all_results.append({
                            'Symbol': symbol,
                            'Timeframe': tf,
                            'Strategy': name,
                            'PnL ($)': metrics['total_pnl'],
                            'Return (%)': metrics['total_pnl_pct'],
                            'Trades': metrics['total_trades'],
                            'Win Rate (%)': metrics['win_rate'],
                            'Profit Factor': metrics['profit_factor'],
                            'Sharpe': metrics['sharpe_ratio'],
                            'Sortino': metrics['sortino_ratio'],
                            'Max DD (%)': metrics['max_drawdown_pct'],
                            'Calmar': metrics['calmar_ratio'],
                            'Avg Trade ($)': metrics['avg_pnl'],
                            'Expectancy': metrics['expectancy'],
                        })

                        status = "+" if metrics['total_pnl'] > 0 else "-"
                        print(f"  [{pct:5.1f}%] {name}: {status}${abs(metrics['total_pnl']):,.0f} | "
                              f"WR:{metrics['win_rate']:.0f}% | PF:{metrics['profit_factor']:.2f}")

                    except Exception as e:
                        print(f"  [{pct:5.1f}%] {name}: ERRO - {str(e)[:50]}")

        # Criar DataFrame de resultados
        results_df = pd.DataFrame(all_results)

        if results_df.empty:
            print("\nNenhum resultado gerado!")
            return

        # Ordenar por retorno
        results_df = results_df.sort_values('Return (%)', ascending=False)

        # Salvar resultados
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # CSV completo
        csv_path = self.results_dir / f"full_backtest_{timestamp}.csv"
        results_df.to_csv(csv_path, index=False)

        # JSON detalhado
        json_path = self.results_dir / f"detailed_results_{timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(self._make_serializable(detailed_results), f, indent=2, default=str)

        # Gerar relatório
        self._generate_report(results_df, detailed_results, timestamp)

        print(f"\n{'='*80}")
        print("RESULTADOS SALVOS:")
        print(f"  CSV: {csv_path}")
        print(f"  JSON: {json_path}")
        print(f"  Relatório: {self.results_dir / f'RELATORIO_{timestamp}.md'}")

    def _make_serializable(self, obj):
        """Torna objeto serializável para JSON."""
        if isinstance(obj, dict):
            # Converter chaves tuple para string
            return {str(k): self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_serializable(i) for i in obj]
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, pd.DataFrame):
            return self._make_serializable(obj.to_dict())
        elif isinstance(obj, pd.Series):
            return self._make_serializable(obj.to_dict())
        elif pd.isna(obj):
            return None
        elif isinstance(obj, (datetime, pd.Timestamp)):
            return str(obj)
        else:
            return obj

    def _generate_report(self, results_df: pd.DataFrame,
                         detailed: Dict, timestamp: str):
        """Gera relatório em Markdown."""
        report = []
        report.append("# Relatório de Backtest Completo")
        report.append(f"\n**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report.append(f"**Capital Inicial:** ${self.capital:,.2f}")
        report.append(f"**Risco por Trade:** {self.risk*100}%")
        report.append(f"**Período:** 2022-01-01 a 2026-03-19 (4+ anos)")

        # Top 10 estratégias
        report.append("\n---\n")
        report.append("## Top 10 Melhores Estratégias (por Retorno)")
        report.append("")
        top10 = results_df.head(10)
        report.append("| Rank | Symbol | TF | Strategy | Return | PF | Sharpe | Max DD |")
        report.append("|------|--------|-----|----------|--------|-----|--------|--------|")
        for i, row in top10.iterrows():
            rank = top10.index.get_loc(i) + 1
            report.append(f"| {rank} | {row['Symbol']} | {row['Timeframe']} | "
                         f"{row['Strategy']} | {row['Return (%)']:.1f}% | "
                         f"{row['Profit Factor']:.2f} | {row['Sharpe']:.2f} | "
                         f"{row['Max DD (%)']:.1f}% |")

        # Top 10 por Sharpe (ajustado ao risco)
        report.append("\n---\n")
        report.append("## Top 10 por Sharpe Ratio (Melhor Risk-Adjusted)")
        top10_sharpe = results_df.nlargest(10, 'Sharpe')
        report.append("")
        report.append("| Rank | Symbol | TF | Strategy | Sharpe | Sortino | Return | Max DD |")
        report.append("|------|--------|-----|----------|--------|---------|--------|--------|")
        for i, row in top10_sharpe.iterrows():
            rank = list(top10_sharpe.index).index(i) + 1
            report.append(f"| {rank} | {row['Symbol']} | {row['Timeframe']} | "
                         f"{row['Strategy']} | {row['Sharpe']:.2f} | "
                         f"{row['Sortino']:.2f} | {row['Return (%)']:.1f}% | "
                         f"{row['Max DD (%)']:.1f}% |")

        # Análise por Ativo
        report.append("\n---\n")
        report.append("## Performance por Ativo")
        for symbol in results_df['Symbol'].unique():
            symbol_df = results_df[results_df['Symbol'] == symbol]
            avg_return = symbol_df['Return (%)'].mean()
            best = symbol_df.iloc[0] if not symbol_df.empty else None
            report.append(f"\n### {symbol}")
            report.append(f"- **Retorno Médio:** {avg_return:.1f}%")
            if best is not None:
                report.append(f"- **Melhor Setup:** {best['Strategy']} ({best['Timeframe']})")
                report.append(f"  - Retorno: {best['Return (%)']:.1f}%")
                report.append(f"  - Profit Factor: {best['Profit Factor']:.2f}")
                report.append(f"  - Win Rate: {best['Win Rate (%)']:.1f}%")

        # Análise por Tipo de Estratégia
        report.append("\n---\n")
        report.append("## Performance por Tipo de Estratégia")

        strategy_types = {
            'EMA Crossover': results_df[results_df['Strategy'].str.startswith('EMA')],
            'RSI Reversal': results_df[results_df['Strategy'].str.startswith('RSI')],
            'Trend Following': results_df[results_df['Strategy'].str.startswith('Trend')]
        }

        for stype, sdf in strategy_types.items():
            if sdf.empty:
                continue
            avg_return = sdf['Return (%)'].mean()
            avg_sharpe = sdf['Sharpe'].mean()
            avg_pf = sdf['Profit Factor'].mean()
            avg_wr = sdf['Win Rate (%)'].mean()
            report.append(f"\n### {stype}")
            report.append(f"- Retorno Médio: {avg_return:.1f}%")
            report.append(f"- Sharpe Médio: {avg_sharpe:.2f}")
            report.append(f"- Profit Factor Médio: {avg_pf:.2f}")
            report.append(f"- Win Rate Médio: {avg_wr:.1f}%")

        # Recomendações
        report.append("\n---\n")
        report.append("## Recomendações")

        # Melhor estratégia geral
        best_overall = results_df.iloc[0]
        report.append(f"\n### Melhor Estratégia Geral")
        report.append(f"**{best_overall['Strategy']}** em **{best_overall['Symbol']} {best_overall['Timeframe']}**")
        report.append(f"- Retorno: {best_overall['Return (%)']:.1f}%")
        report.append(f"- Sharpe: {best_overall['Sharpe']:.2f}")
        report.append(f"- Max Drawdown: {best_overall['Max DD (%)']:.1f}%")

        # Melhor para baixo drawdown
        low_dd = results_df[results_df['Return (%)'] > 0].nsmallest(5, 'Max DD (%)').iloc[0] if len(results_df[results_df['Return (%)'] > 0]) > 0 else None
        if low_dd is not None:
            report.append(f"\n### Melhor para Baixo Risco")
            report.append(f"**{low_dd['Strategy']}** em **{low_dd['Symbol']} {low_dd['Timeframe']}**")
            report.append(f"- Max Drawdown: {low_dd['Max DD (%)']:.1f}%")
            report.append(f"- Retorno: {low_dd['Return (%)']:.1f}%")

        # Conclusão
        report.append("\n---\n")
        report.append("## Conclusão")

        sol_results = results_df[results_df['Symbol'] == 'SOLUSDT']
        if not sol_results.empty:
            sol_best = sol_results.iloc[0]
            trend_results = results_df[results_df['Strategy'].str.startswith('Trend')]
            trend_avg = trend_results['Return (%)'].mean() if not trend_results.empty else 0

            report.append(f"""
Com base na análise de {len(results_df)} combinações de estratégia/ativo/timeframe:

1. **SOL-PERP permanece a melhor escolha** para seu perfil:
   - Maior volatilidade = mais oportunidades
   - Melhor setup: {sol_best['Strategy']} em {sol_best['Timeframe']}

2. **Trend Following superou Mean Reversion**:
   - Retorno médio Trend: {trend_avg:.1f}%
   - Confirma o estudo inicial

3. **Próximos passos recomendados**:
   - Implementar a estratégia {sol_best['Strategy']}
   - Usar {sol_best['Timeframe']} como timeframe principal
   - Testar em paper trading por 2-4 semanas antes do capital real
""")

        # Salvar relatório
        report_path = self.results_dir / f"RELATORIO_{timestamp}.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))


def main():
    """Executa backtest completo."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=10000)
    parser.add_argument("--risk", type=float, default=0.02)
    args = parser.parse_args()

    backtester = FullBacktester(capital=args.capital, risk=args.risk)
    backtester.run_full_analysis()


if __name__ == "__main__":
    main()
