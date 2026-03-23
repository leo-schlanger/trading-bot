// Trade history endpoint

export async function onRequestGet(context) {
  const { env, request } = context;

  try {
    const url = new URL(request.url);
    const limit = parseInt(url.searchParams.get('limit') || '100');
    const offset = parseInt(url.searchParams.get('offset') || '0');
    const asset = url.searchParams.get('asset'); // BTC, ETH, or null for all

    // Get trade history from KV
    const historyData = await env.TRADING_KV.get('trade_history');

    if (!historyData) {
      return Response.json({
        success: true,
        trades: [],
        total: 0,
        message: 'No trade history available yet'
      });
    }

    let trades = JSON.parse(historyData);

    // Filter by asset if specified
    if (asset) {
      trades = trades.filter(t => t.symbol === asset || t.asset === asset);
    }

    // Sort by timestamp descending (most recent first)
    trades.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    const total = trades.length;

    // Apply pagination
    const paginatedTrades = trades.slice(offset, offset + limit);

    // Calculate statistics
    const stats = calculateTradeStats(trades);

    return Response.json({
      success: true,
      trades: paginatedTrades,
      total: total,
      offset: offset,
      limit: limit,
      stats: stats
    });
  } catch (error) {
    return Response.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}

function calculateTradeStats(trades) {
  if (trades.length === 0) {
    return {
      totalTrades: 0,
      wins: 0,
      losses: 0,
      winRate: 0,
      totalPnL: 0,
      avgPnL: 0,
      bestTrade: 0,
      worstTrade: 0,
      profitFactor: 0
    };
  }

  const closedTrades = trades.filter(t => t.pnl !== undefined && t.pnl !== null);

  if (closedTrades.length === 0) {
    return {
      totalTrades: trades.length,
      closedTrades: 0,
      openTrades: trades.length,
      wins: 0,
      losses: 0,
      winRate: 0,
      totalPnL: 0,
      avgPnL: 0,
      bestTrade: 0,
      worstTrade: 0,
      profitFactor: 0
    };
  }

  const wins = closedTrades.filter(t => t.pnl > 0);
  const losses = closedTrades.filter(t => t.pnl <= 0);

  const totalPnL = closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
  const grossProfit = wins.reduce((sum, t) => sum + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((sum, t) => sum + t.pnl, 0));

  const pnls = closedTrades.map(t => t.pnl);

  return {
    totalTrades: trades.length,
    closedTrades: closedTrades.length,
    openTrades: trades.length - closedTrades.length,
    wins: wins.length,
    losses: losses.length,
    winRate: closedTrades.length > 0 ? (wins.length / closedTrades.length) : 0,
    totalPnL: totalPnL,
    avgPnL: closedTrades.length > 0 ? totalPnL / closedTrades.length : 0,
    bestTrade: Math.max(...pnls, 0),
    worstTrade: Math.min(...pnls, 0),
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0
  };
}
