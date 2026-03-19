"""
Métricas de performance para backtest.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any
from .position import Trade


def calculate_metrics(trades: List[Trade],
                      equity_curve: pd.Series,
                      initial_capital: float,
                      risk_free_rate: float = 0.0) -> Dict[str, Any]:
    """
    Calcula todas as métricas de performance.
    """
    if not trades:
        return _empty_metrics()

    # Converter trades para arrays
    pnls = np.array([t.pnl for t in trades])
    pnl_pcts = np.array([t.pnl_pct for t in trades])
    winners = pnls > 0
    losers = pnls < 0

    # Métricas básicas
    total_trades = len(trades)
    winning_trades = np.sum(winners)
    losing_trades = np.sum(losers)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0

    # PnL
    total_pnl = np.sum(pnls)
    total_pnl_pct = (equity_curve.iloc[-1] - initial_capital) / initial_capital
    avg_pnl = np.mean(pnls)
    avg_pnl_pct = np.mean(pnl_pcts)

    # Winners vs Losers
    avg_win = np.mean(pnls[winners]) if winning_trades > 0 else 0
    avg_loss = np.mean(pnls[losers]) if losing_trades > 0 else 0
    avg_win_pct = np.mean(pnl_pcts[winners]) if winning_trades > 0 else 0
    avg_loss_pct = np.mean(pnl_pcts[losers]) if losing_trades > 0 else 0

    # Maior win/loss
    max_win = np.max(pnls) if winning_trades > 0 else 0
    max_loss = np.min(pnls) if losing_trades > 0 else 0

    # Profit Factor
    gross_profit = np.sum(pnls[winners]) if winning_trades > 0 else 0
    gross_loss = abs(np.sum(pnls[losers])) if losing_trades > 0 else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Expectancy (valor esperado por trade)
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
    expectancy_r = avg_win / abs(avg_loss) if avg_loss != 0 else float('inf')

    # Drawdown
    peak = equity_curve.expanding().max()
    drawdown = equity_curve - peak
    drawdown_pct = drawdown / peak
    max_drawdown = drawdown.min()
    max_drawdown_pct = drawdown_pct.min()

    # Recovery factor
    recovery_factor = total_pnl / abs(max_drawdown) if max_drawdown != 0 else float('inf')

    # Calmar Ratio (retorno anualizado / max drawdown)
    trading_days = len(equity_curve)
    annual_factor = 365 / trading_days if trading_days > 0 else 1
    annual_return = total_pnl_pct * annual_factor
    calmar_ratio = annual_return / abs(max_drawdown_pct) if max_drawdown_pct != 0 else float('inf')

    # Sharpe Ratio
    returns = equity_curve.pct_change().dropna()
    if len(returns) > 1:
        sharpe = _calculate_sharpe(returns, risk_free_rate)
        sortino = _calculate_sortino(returns, risk_free_rate)
    else:
        sharpe = 0
        sortino = 0

    # Streaks
    max_consecutive_wins = _max_consecutive(winners)
    max_consecutive_losses = _max_consecutive(losers)

    # Duração média dos trades
    durations = [t.duration for t in trades]
    avg_duration = np.mean(durations)
    avg_win_duration = np.mean([t.duration for t in trades if t.is_winner]) if winning_trades > 0 else 0
    avg_loss_duration = np.mean([t.duration for t in trades if not t.is_winner]) if losing_trades > 0 else 0

    # Fees totais
    total_fees = sum(t.fees for t in trades)

    return {
        # Performance geral
        'total_pnl': total_pnl,
        'total_pnl_pct': total_pnl_pct * 100,
        'annual_return_pct': annual_return * 100,

        # Trades
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'win_rate': win_rate * 100,

        # PnL médio
        'avg_pnl': avg_pnl,
        'avg_pnl_pct': avg_pnl_pct * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'avg_win_pct': avg_win_pct * 100,
        'avg_loss_pct': avg_loss_pct * 100,

        # Extremos
        'max_win': max_win,
        'max_loss': max_loss,

        # Ratios
        'profit_factor': profit_factor,
        'expectancy': expectancy,
        'expectancy_r': expectancy_r,
        'risk_reward_ratio': abs(avg_win / avg_loss) if avg_loss != 0 else float('inf'),

        # Drawdown
        'max_drawdown': max_drawdown,
        'max_drawdown_pct': max_drawdown_pct * 100,
        'recovery_factor': recovery_factor,
        'calmar_ratio': calmar_ratio,

        # Risk-adjusted
        'sharpe_ratio': sharpe,
        'sortino_ratio': sortino,

        # Streaks
        'max_consecutive_wins': max_consecutive_wins,
        'max_consecutive_losses': max_consecutive_losses,

        # Tempo
        'avg_trade_duration_hours': avg_duration,
        'avg_win_duration_hours': avg_win_duration,
        'avg_loss_duration_hours': avg_loss_duration,

        # Custos
        'total_fees': total_fees,

        # Capital
        'initial_capital': initial_capital,
        'final_capital': equity_curve.iloc[-1],
    }


def _calculate_sharpe(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Sharpe Ratio anualizado."""
    excess_returns = returns - (risk_free_rate / 252)
    if returns.std() == 0:
        return 0
    return np.sqrt(252) * excess_returns.mean() / returns.std()


def _calculate_sortino(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Sortino Ratio - usa apenas volatilidade negativa."""
    excess_returns = returns - (risk_free_rate / 252)
    downside_returns = returns[returns < 0]

    if len(downside_returns) == 0 or downside_returns.std() == 0:
        return float('inf') if excess_returns.mean() > 0 else 0

    return np.sqrt(252) * excess_returns.mean() / downside_returns.std()


def _max_consecutive(bool_array: np.ndarray) -> int:
    """Máximo de valores True consecutivos."""
    if len(bool_array) == 0:
        return 0

    max_streak = 0
    current_streak = 0

    for val in bool_array:
        if val:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    return max_streak


def _empty_metrics() -> Dict[str, Any]:
    """Retorna métricas vazias quando não há trades."""
    return {
        'total_pnl': 0,
        'total_pnl_pct': 0,
        'annual_return_pct': 0,
        'total_trades': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'win_rate': 0,
        'avg_pnl': 0,
        'avg_pnl_pct': 0,
        'avg_win': 0,
        'avg_loss': 0,
        'avg_win_pct': 0,
        'avg_loss_pct': 0,
        'max_win': 0,
        'max_loss': 0,
        'profit_factor': 0,
        'expectancy': 0,
        'expectancy_r': 0,
        'risk_reward_ratio': 0,
        'max_drawdown': 0,
        'max_drawdown_pct': 0,
        'recovery_factor': 0,
        'calmar_ratio': 0,
        'sharpe_ratio': 0,
        'sortino_ratio': 0,
        'max_consecutive_wins': 0,
        'max_consecutive_losses': 0,
        'avg_trade_duration_hours': 0,
        'avg_win_duration_hours': 0,
        'avg_loss_duration_hours': 0,
        'total_fees': 0,
        'initial_capital': 0,
        'final_capital': 0,
    }


def print_metrics(metrics: Dict[str, Any]):
    """Imprime métricas formatadas."""
    print("\n" + "=" * 60)
    print("RESULTADOS DO BACKTEST")
    print("=" * 60)

    print(f"\n📊 PERFORMANCE GERAL")
    print(f"   PnL Total: ${metrics['total_pnl']:,.2f} ({metrics['total_pnl_pct']:.2f}%)")
    print(f"   Retorno Anualizado: {metrics['annual_return_pct']:.2f}%")
    print(f"   Capital Final: ${metrics['final_capital']:,.2f}")

    print(f"\n📈 TRADES")
    print(f"   Total: {metrics['total_trades']}")
    print(f"   Wins: {metrics['winning_trades']} | Losses: {metrics['losing_trades']}")
    print(f"   Win Rate: {metrics['win_rate']:.1f}%")
    print(f"   Avg Win: ${metrics['avg_win']:,.2f} ({metrics['avg_win_pct']:.2f}%)")
    print(f"   Avg Loss: ${metrics['avg_loss']:,.2f} ({metrics['avg_loss_pct']:.2f}%)")

    print(f"\n⚖️ RATIOS")
    print(f"   Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"   Risk/Reward: {metrics['risk_reward_ratio']:.2f}")
    print(f"   Expectancy: ${metrics['expectancy']:,.2f}")
    print(f"   Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"   Sortino Ratio: {metrics['sortino_ratio']:.2f}")

    print(f"\n📉 RISCO")
    print(f"   Max Drawdown: ${metrics['max_drawdown']:,.2f} ({metrics['max_drawdown_pct']:.2f}%)")
    print(f"   Recovery Factor: {metrics['recovery_factor']:.2f}")
    print(f"   Calmar Ratio: {metrics['calmar_ratio']:.2f}")

    print(f"\n🔥 STREAKS")
    print(f"   Max Wins Consecutivos: {metrics['max_consecutive_wins']}")
    print(f"   Max Losses Consecutivos: {metrics['max_consecutive_losses']}")

    print(f"\n⏱️ TEMPO")
    print(f"   Duração Média Trade: {metrics['avg_trade_duration_hours']:.1f}h")

    print(f"\n💸 CUSTOS")
    print(f"   Total Fees: ${metrics['total_fees']:,.2f}")

    print("=" * 60)
