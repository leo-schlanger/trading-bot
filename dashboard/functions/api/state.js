// Bot state endpoint - returns current trading state

export async function onRequestGet(context) {
  const { env } = context;

  try {
    // Get current bot state from KV
    const stateData = await env.TRADING_KV.get('trading_state');

    if (!stateData) {
      return Response.json({
        success: true,
        state: null,
        message: 'No state data available yet'
      });
    }

    const state = JSON.parse(stateData);

    // Get decision log if available
    const decisionsData = await env.TRADING_KV.get('decision_log');
    const decisions = decisionsData ? JSON.parse(decisionsData) : [];

    // Get open positions if available
    const positionsData = await env.TRADING_KV.get('open_positions');
    const positions = positionsData ? JSON.parse(positionsData) : {};

    // Get safety events if available
    const safetyData = await env.TRADING_KV.get('safety_events');
    const safetyEvents = safetyData ? JSON.parse(safetyData) : [];

    // Calculate portfolio summary
    const portfolioSummary = {
      capital: state.capital || 500,
      totalPnl: state.total_pnl || 0,
      totalTrades: state.total_trades || 0,
      winningTrades: state.winning_trades || 0,
      losingTrades: state.losing_trades || 0,
      winRate: state.total_trades > 0 ? (state.winning_trades || 0) / state.total_trades : 0,
      consecutiveLosses: state.consecutive_losses || 0,
      consecutiveWins: state.consecutive_wins || 0,
      openPositions: Object.keys(positions).length || Object.keys(state.positions || {}).length
    };

    // Calculate safety status
    const consecutiveLosses = state.consecutive_losses || 0;
    const riskState = state.risk_state || {};
    const capital = state.capital || 500;
    const peak = riskState.peak || 500;
    const currentDrawdown = peak > 0 ? ((peak - capital) / peak) * 100 : 0;

    const warnings = [];
    if (consecutiveLosses >= 2) warnings.push(`${consecutiveLosses} consecutive losses`);
    if (currentDrawdown >= 10) warnings.push(`Drawdown at ${currentDrawdown.toFixed(1)}%`);

    const safetyStatus = {
      blocked: consecutiveLosses >= 3 || currentDrawdown >= 20,
      warnings: warnings,
      consecutiveLosses: consecutiveLosses,
      currentDrawdown: currentDrawdown
    };

    return Response.json({
      success: true,
      state: state,
      positions: positions || state.positions || {},
      decisions: decisions.slice(-50), // Last 50 decisions
      safetyEvents: safetyEvents.slice(-20), // Last 20 safety events
      portfolioSummary: portfolioSummary,
      safetyStatus: safetyStatus,
      lastUpdate: state.last_run || null
    });
  } catch (error) {
    return Response.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}
