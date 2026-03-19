"""
Validação do backtest - mostra passo a passo.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np

from src.backtest.engine import BacktestEngine, BacktestConfig
from strategies.advanced_strategies import DonchianBreakoutStrategy, MomentumBreakoutStrategy

# Carregar dados
data_path = Path(__file__).parent / "data" / "raw" / "SOLUSDT_4h.csv"
print(f"Carregando: {data_path}")
print(f"Arquivo existe: {data_path.exists()}")

df = pd.read_csv(data_path, index_col=0, parse_dates=True)

print(f"\n=== DADOS CARREGADOS ===")
print(f"Total de candles: {len(df)}")
print(f"Período: {df.index.min()} a {df.index.max()}")
print(f"Colunas: {list(df.columns)}")
print(f"\nPrimeiras 3 linhas:")
print(df.head(3))
print(f"\nÚltimas 3 linhas:")
print(df.tail(3))

# Estatísticas dos dados
print(f"\n=== ESTATÍSTICAS DOS DADOS ===")
print(f"Preço inicial: ${df['close'].iloc[0]:.2f}")
print(f"Preço final: ${df['close'].iloc[-1]:.2f}")
print(f"Preço máximo: ${df['high'].max():.2f}")
print(f"Preço mínimo: ${df['low'].min():.2f}")
print(f"Variação total: {((df['close'].iloc[-1] / df['close'].iloc[0]) - 1) * 100:.1f}%")

# Configurar backtest
config = BacktestConfig(
    initial_capital=10000,
    risk_per_trade=0.02,
    maker_fee=0.0002,
    taker_fee=0.001,
    slippage=0.0005
)

print(f"\n=== CONFIGURAÇÃO DO BACKTEST ===")
print(f"Capital inicial: ${config.initial_capital}")
print(f"Risco por trade: {config.risk_per_trade * 100}%")
print(f"Taxa maker: {config.maker_fee * 100}%")
print(f"Taxa taker: {config.taker_fee * 100}%")
print(f"Slippage: {config.slippage * 100}%")

# Testar estratégia Donchian
print(f"\n{'='*60}")
print("TESTE 1: Donchian_20_10 em SOL 4h")
print('='*60)

strategy = DonchianBreakoutStrategy(entry_period=20, exit_period=10, atr_sl_mult=2.0)
engine = BacktestEngine(config)
results = engine.run(df.copy(), strategy, verbose=False)

m = results['metrics']
trades = results['trades']

print(f"\nResultados:")
print(f"  PnL Total: ${m['total_pnl']:.2f}")
print(f"  Retorno: {m['total_pnl_pct']:.2f}%")
print(f"  Total trades: {m['total_trades']}")
print(f"  Win Rate: {m['win_rate']:.1f}%")
print(f"  Avg Win: ${m['avg_win']:.2f} ({m['avg_win_pct']:.2f}%)")
print(f"  Avg Loss: ${m['avg_loss']:.2f} ({m['avg_loss_pct']:.2f}%)")
print(f"  Risk/Reward: {m['risk_reward_ratio']:.2f}")
print(f"  Profit Factor: {m['profit_factor']:.2f}")
print(f"  Max Drawdown: {m['max_drawdown_pct']:.2f}%")
print(f"  Sharpe Ratio: {m['sharpe_ratio']:.3f}")

# Mostrar alguns trades
print(f"\nPrimeiros 5 trades:")
for i, t in enumerate(trades[:5]):
    side = "LONG" if t.side.value == 1 else "SHORT"
    result = "WIN" if t.is_winner else "LOSS"
    print(f"  {i+1}. {t.entry_time.strftime('%Y-%m-%d')} | {side} | "
          f"Entry: ${t.entry_price:.2f} -> Exit: ${t.exit_price:.2f} | "
          f"PnL: ${t.pnl:.2f} ({t.pnl_pct*100:.1f}%) | {result}")

print(f"\nÚltimos 5 trades:")
for i, t in enumerate(trades[-5:]):
    side = "LONG" if t.side.value == 1 else "SHORT"
    result = "WIN" if t.is_winner else "LOSS"
    print(f"  {len(trades)-4+i}. {t.entry_time.strftime('%Y-%m-%d')} | {side} | "
          f"Entry: ${t.entry_price:.2f} -> Exit: ${t.exit_price:.2f} | "
          f"PnL: ${t.pnl:.2f} ({t.pnl_pct*100:.1f}%) | {result}")

# Equity curve
equity = results['equity_curve']
print(f"\nEquity Curve:")
print(f"  Inicial: ${equity.iloc[0]:.2f}")
print(f"  Final: ${equity.iloc[-1]:.2f}")
print(f"  Máximo: ${equity.max():.2f}")
print(f"  Mínimo: ${equity.min():.2f}")

# Testar segunda estratégia
print(f"\n{'='*60}")
print("TESTE 2: Momentum_Standard em SOL 4h")
print('='*60)

strategy2 = MomentumBreakoutStrategy(momentum_period=14, volume_threshold=1.5)
engine2 = BacktestEngine(config)
results2 = engine2.run(df.copy(), strategy2, verbose=False)

m2 = results2['metrics']
trades2 = results2['trades']

print(f"\nResultados:")
print(f"  PnL Total: ${m2['total_pnl']:.2f}")
print(f"  Retorno: {m2['total_pnl_pct']:.2f}%")
print(f"  Total trades: {m2['total_trades']}")
print(f"  Win Rate: {m2['win_rate']:.1f}%")
print(f"  Profit Factor: {m2['profit_factor']:.2f}")
print(f"  Expectancy: ${m2['expectancy']:.2f}/trade")

print(f"\nPrimeiros 5 trades:")
for i, t in enumerate(trades2[:5]):
    side = "LONG" if t.side.value == 1 else "SHORT"
    result = "WIN" if t.is_winner else "LOSS"
    print(f"  {i+1}. {t.entry_time.strftime('%Y-%m-%d')} | {side} | "
          f"Entry: ${t.entry_price:.2f} -> Exit: ${t.exit_price:.2f} | "
          f"PnL: ${t.pnl:.2f} | {result}")

print(f"\n{'='*60}")
print("VALIDAÇÃO COMPLETA - Backtests executados nos dados locais")
print('='*60)
