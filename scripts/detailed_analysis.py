"""
Análise detalhada de Win Rate, Avg Win, Avg Loss por estratégia.
"""

import pandas as pd
import json
from pathlib import Path

results_dir = Path(__file__).parent.parent / "results"

# Encontrar último arquivo JSON
json_files = list(results_dir.glob("detailed_results_*.json"))
if not json_files:
    print("Nenhum arquivo de resultados encontrado!")
    exit()

latest_json = sorted(json_files)[-1]
print(f"Analisando: {latest_json.name}\n")

with open(latest_json, 'r') as f:
    data = json.load(f)

# Coletar métricas detalhadas
rows = []
for symbol, timeframes in data.items():
    for tf, strategies in timeframes.items():
        for strat_name, strat_data in strategies.items():
            m = strat_data.get('metrics', {})
            if not m:
                continue

            rows.append({
                'Ativo': symbol.replace('USDT', ''),
                'TF': tf,
                'Estratégia': strat_name,
                'Trades': m.get('total_trades', 0),
                'Win Rate %': round(m.get('win_rate', 0), 1),
                'Avg Win $': round(m.get('avg_win', 0), 2),
                'Avg Win %': round(m.get('avg_win_pct', 0), 2),
                'Avg Loss $': round(m.get('avg_loss', 0), 2),
                'Avg Loss %': round(m.get('avg_loss_pct', 0), 2),
                'Max Win $': round(m.get('max_win', 0), 2),
                'Max Loss $': round(m.get('max_loss', 0), 2),
                'Risk/Reward': round(m.get('risk_reward_ratio', 0), 2),
                'Profit Factor': round(m.get('profit_factor', 0), 2),
                'Expectancy $': round(m.get('expectancy', 0), 2),
                'Retorno %': round(m.get('total_pnl_pct', 0), 1),
                'Max DD %': round(m.get('max_drawdown_pct', 0), 1),
                'Sharpe': round(m.get('sharpe_ratio', 0), 3),
                'Wins Consec': m.get('max_consecutive_wins', 0),
                'Losses Consec': m.get('max_consecutive_losses', 0),
            })

df = pd.DataFrame(rows)

# Ordenar por retorno
df = df.sort_values('Retorno %', ascending=False)

print("=" * 100)
print("ANÁLISE DETALHADA - WIN/LOSS POR ESTRATÉGIA")
print("=" * 100)

# Top 10 por retorno com detalhes de win/loss
print("\n### TOP 10 POR RETORNO ###\n")
top10 = df.head(10)
for i, row in top10.iterrows():
    print(f"{row['Ativo']} {row['TF']} | {row['Estratégia']}")
    print(f"  Retorno: {row['Retorno %']:+.1f}% | Trades: {row['Trades']}")
    print(f"  Win Rate: {row['Win Rate %']:.1f}% | R/R: {row['Risk/Reward']:.2f}")
    print(f"  Avg Win: ${row['Avg Win $']:.2f} ({row['Avg Win %']:.2f}%)")
    print(f"  Avg Loss: ${row['Avg Loss $']:.2f} ({row['Avg Loss %']:.2f}%)")
    print(f"  Max Win: ${row['Max Win $']:.2f} | Max Loss: ${row['Max Loss $']:.2f}")
    print(f"  Expectancy: ${row['Expectancy $']:.2f}/trade")
    print(f"  Max Consecutive: {row['Wins Consec']} wins, {row['Losses Consec']} losses")
    print()

# Análise por tipo de estratégia
print("\n### ANÁLISE POR TIPO DE ESTRATÉGIA ###\n")

strategy_types = {
    'EMA Crossover': df[df['Estratégia'].str.startswith('EMA')],
    'RSI Reversal': df[df['Estratégia'].str.startswith('RSI')],
    'Trend Following': df[df['Estratégia'].str.startswith('Trend')]
}

for stype, sdf in strategy_types.items():
    if sdf.empty:
        continue
    print(f"--- {stype} ---")
    print(f"  Retorno Médio: {sdf['Retorno %'].mean():.1f}%")
    print(f"  Win Rate Médio: {sdf['Win Rate %'].mean():.1f}%")
    print(f"  Avg Win Médio: ${sdf['Avg Win $'].mean():.2f} ({sdf['Avg Win %'].mean():.2f}%)")
    print(f"  Avg Loss Médio: ${sdf['Avg Loss $'].mean():.2f} ({sdf['Avg Loss %'].mean():.2f}%)")
    print(f"  Risk/Reward Médio: {sdf['Risk/Reward'].mean():.2f}")
    print(f"  Profit Factor Médio: {sdf['Profit Factor'].mean():.2f}")
    print(f"  Melhor setup: {sdf.iloc[0]['Ativo']} {sdf.iloc[0]['TF']} ({sdf.iloc[0]['Retorno %']:+.1f}%)")
    print()

# Análise por ativo
print("\n### ANÁLISE POR ATIVO ###\n")

for ativo in ['SOL', 'BTC', 'ETH']:
    adf = df[df['Ativo'] == ativo]
    if adf.empty:
        continue
    print(f"--- {ativo} ---")
    print(f"  Retorno Médio: {adf['Retorno %'].mean():.1f}%")
    print(f"  Win Rate Médio: {adf['Win Rate %'].mean():.1f}%")
    print(f"  Avg Win: ${adf['Avg Win $'].mean():.2f} | Avg Loss: ${adf['Avg Loss $'].mean():.2f}")
    best = adf.iloc[0]
    print(f"  Melhor: {best['Estratégia']} {best['TF']} ({best['Retorno %']:+.1f}%)")
    print()

# Análise por timeframe
print("\n### ANÁLISE POR TIMEFRAME ###\n")

for tf in ['1h', '4h']:
    tdf = df[df['TF'] == tf]
    if tdf.empty:
        continue
    profitable = len(tdf[tdf['Retorno %'] > 0])
    print(f"--- {tf} ---")
    print(f"  Estratégias lucrativas: {profitable}/{len(tdf)} ({100*profitable/len(tdf):.0f}%)")
    print(f"  Retorno Médio: {tdf['Retorno %'].mean():.1f}%")
    print(f"  Win Rate Médio: {tdf['Win Rate %'].mean():.1f}%")
    print(f"  Profit Factor Médio: {tdf['Profit Factor'].mean():.2f}")
    print()

# Salvar análise detalhada
output_path = results_dir / "analise_detalhada.csv"
df.to_csv(output_path, index=False)
print(f"\nAnálise salva em: {output_path}")

# Criar relatório markdown
md_path = results_dir / "ANALISE_WINLOSS.md"
with open(md_path, 'w', encoding='utf-8') as f:
    f.write("# Análise Detalhada Win/Loss\n\n")
    f.write("## Top 10 Estratégias por Retorno\n\n")
    f.write("| Ativo | TF | Estratégia | Ret% | WinRate | AvgWin% | AvgLoss% | R/R | PF | Expect$ |\n")
    f.write("|-------|-----|------------|------|---------|---------|----------|-----|-----|--------|\n")
    for i, row in df.head(10).iterrows():
        f.write(f"| {row['Ativo']} | {row['TF']} | {row['Estratégia']} | ")
        f.write(f"{row['Retorno %']:+.1f} | {row['Win Rate %']:.0f}% | ")
        f.write(f"{row['Avg Win %']:.1f}% | {row['Avg Loss %']:.1f}% | ")
        f.write(f"{row['Risk/Reward']:.2f} | {row['Profit Factor']:.2f} | ")
        f.write(f"${row['Expectancy $']:.2f} |\n")

print(f"Relatório MD salvo em: {md_path}")
