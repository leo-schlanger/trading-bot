// Performance metrics endpoint

export async function onRequestGet(context) {
  const { env, request } = context;

  try {
    const url = new URL(request.url);
    const period = url.searchParams.get('period') || 'all'; // all, 7d, 30d, 90d

    // Get all required data
    const [stateData, historyData, metricsData] = await Promise.all([
      env.TRADING_KV.get('trading_state'),
      env.TRADING_KV.get('trade_history'),
      env.TRADING_KV.get('performance_metrics')
    ]);

    const state = stateData ? JSON.parse(stateData) : null;
    const trades = historyData ? JSON.parse(historyData) : [];
    const storedMetrics = metricsData ? JSON.parse(metricsData) : null;

    // Filter trades by period
    const filteredTrades = filterByPeriod(trades, period);

    // Calculate metrics
    const metrics = calculateMetrics(filteredTrades, state);

    // Get regime history
    const regimeData = await env.TRADING_KV.get('regime_history');
    const regimeHistory = regimeData ? JSON.parse(regimeData) : [];

    // Get equity curve
    const equityData = await env.TRADING_KV.get('equity_curve');
    const equityCurve = equityData ? JSON.parse(equityData) : [];

    return Response.json({
      success: true,
      period: period,
      metrics: metrics,
      regimeHistory: regimeHistory.slice(-100),
      equityCurve: equityCurve.slice(-365), // Last year of daily data
      storedMetrics: storedMetrics
    });
  } catch (error) {
    return Response.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}

function filterByPeriod(trades, period) {
  if (period === 'all') return trades;

  const now = new Date();
  let cutoff;

  switch (period) {
    case '7d':
      cutoff = new Date(now - 7 * 24 * 60 * 60 * 1000);
      break;
    case '30d':
      cutoff = new Date(now - 30 * 24 * 60 * 60 * 1000);
      break;
    case '90d':
      cutoff = new Date(now - 90 * 24 * 60 * 60 * 1000);
      break;
    default:
      return trades;
  }

  return trades.filter(t => new Date(t.timestamp) >= cutoff);
}

function calculateMetrics(trades, state) {
  const closedTrades = trades.filter(t => t.pnl !== undefined && t.pnl !== null);

  if (closedTrades.length === 0) {
    return {
      sharpeRatio: 0,
      sortinoRatio: 0,
      maxDrawdown: 0,
      currentDrawdown: 0,
      avgHoldingTime: 0,
      avgWin: 0,
      avgLoss: 0,
      largestWin: 0,
      largestLoss: 0,
      consecutiveWins: 0,
      consecutiveLosses: 0,
      currentStreak: 0,
      expectancy: 0,
      riskRewardRatio: 0,
      calmarRatio: 0,
      recoveryFactor: 0,
      totalReturn: 0,
      annualizedReturn: 0,
      volatility: 0,
      tradesByAsset: {},
      tradesByStrategy: {},
      tradesByRegime: {}
    };
  }

  // Calculate returns
  const returns = closedTrades.map(t => t.pnl_pct || (t.pnl / (state?.capital || 500) * 100));
  const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
  const stdDev = Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length);

  // Downside deviation for Sortino
  const negReturns = returns.filter(r => r < 0);
  const downsideDev = negReturns.length > 0
    ? Math.sqrt(negReturns.reduce((sum, r) => sum + Math.pow(r, 2), 0) / negReturns.length)
    : 1;

  // Sharpe and Sortino (assuming 0% risk-free rate)
  const sharpeRatio = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(252) : 0;
  const sortinoRatio = downsideDev > 0 ? (avgReturn / downsideDev) * Math.sqrt(252) : 0;

  // Win/Loss analysis
  const wins = closedTrades.filter(t => t.pnl > 0);
  const losses = closedTrades.filter(t => t.pnl <= 0);
  const avgWin = wins.length > 0 ? wins.reduce((sum, t) => sum + t.pnl, 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((sum, t) => sum + t.pnl, 0) / losses.length) : 0;

  // Expectancy
  const winRate = wins.length / closedTrades.length;
  const expectancy = (winRate * avgWin) - ((1 - winRate) * avgLoss);

  // Risk/Reward Ratio
  const riskRewardRatio = avgLoss > 0 ? avgWin / avgLoss : avgWin > 0 ? Infinity : 0;

  // Consecutive streaks
  let maxConsecWins = 0, maxConsecLosses = 0, currentStreak = 0;
  let consecWins = 0, consecLosses = 0;

  closedTrades.forEach(t => {
    if (t.pnl > 0) {
      consecWins++;
      consecLosses = 0;
      maxConsecWins = Math.max(maxConsecWins, consecWins);
      currentStreak = consecWins;
    } else {
      consecLosses++;
      consecWins = 0;
      maxConsecLosses = Math.max(maxConsecLosses, consecLosses);
      currentStreak = -consecLosses;
    }
  });

  // Drawdown calculation
  let peak = state?.capital || 500;
  let maxDrawdown = 0;
  let equity = peak;

  closedTrades.forEach(t => {
    equity += t.pnl || 0;
    peak = Math.max(peak, equity);
    const drawdown = (peak - equity) / peak * 100;
    maxDrawdown = Math.max(maxDrawdown, drawdown);
  });

  const currentDrawdown = ((peak - equity) / peak * 100);

  // Total return
  const initialCapital = state?.capital || 500;
  const totalPnL = closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
  const totalReturn = (totalPnL / initialCapital) * 100;

  // Group by categories
  const tradesByAsset = {};
  const tradesByStrategy = {};
  const tradesByRegime = {};

  closedTrades.forEach(t => {
    // By asset
    const asset = t.asset || 'Unknown';
    if (!tradesByAsset[asset]) tradesByAsset[asset] = { count: 0, pnl: 0, wins: 0 };
    tradesByAsset[asset].count++;
    tradesByAsset[asset].pnl += t.pnl || 0;
    if (t.pnl > 0) tradesByAsset[asset].wins++;

    // By strategy
    const strategy = t.strategy || 'Unknown';
    if (!tradesByStrategy[strategy]) tradesByStrategy[strategy] = { count: 0, pnl: 0, wins: 0 };
    tradesByStrategy[strategy].count++;
    tradesByStrategy[strategy].pnl += t.pnl || 0;
    if (t.pnl > 0) tradesByStrategy[strategy].wins++;

    // By regime
    const regime = t.regime || 'Unknown';
    if (!tradesByRegime[regime]) tradesByRegime[regime] = { count: 0, pnl: 0, wins: 0 };
    tradesByRegime[regime].count++;
    tradesByRegime[regime].pnl += t.pnl || 0;
    if (t.pnl > 0) tradesByRegime[regime].wins++;
  });

  // Holding time
  const holdingTimes = closedTrades
    .filter(t => t.entry_time && t.exit_time)
    .map(t => (new Date(t.exit_time) - new Date(t.entry_time)) / (1000 * 60 * 60)); // hours

  const avgHoldingTime = holdingTimes.length > 0
    ? holdingTimes.reduce((a, b) => a + b, 0) / holdingTimes.length
    : 0;

  return {
    sharpeRatio: sharpeRatio.toFixed(2),
    sortinoRatio: sortinoRatio.toFixed(2),
    maxDrawdown: maxDrawdown.toFixed(2),
    currentDrawdown: currentDrawdown.toFixed(2),
    avgHoldingTime: avgHoldingTime.toFixed(1),
    avgWin: avgWin.toFixed(2),
    avgLoss: avgLoss.toFixed(2),
    largestWin: Math.max(...closedTrades.map(t => t.pnl || 0)).toFixed(2),
    largestLoss: Math.min(...closedTrades.map(t => t.pnl || 0)).toFixed(2),
    consecutiveWins: maxConsecWins,
    consecutiveLosses: maxConsecLosses,
    currentStreak: currentStreak,
    expectancy: expectancy.toFixed(2),
    riskRewardRatio: riskRewardRatio.toFixed(2),
    totalReturn: totalReturn.toFixed(2),
    volatility: (stdDev * Math.sqrt(252)).toFixed(2),
    calmarRatio: maxDrawdown > 0 ? (totalReturn / maxDrawdown).toFixed(2) : 0,
    win_rate: winRate,
    tradesByAsset,
    tradesByStrategy,
    tradesByRegime
  };
}
