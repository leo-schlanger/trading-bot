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

    // Get safety events if available
    const safetyData = await env.TRADING_KV.get('safety_events');
    const safetyEvents = safetyData ? JSON.parse(safetyData) : [];

    return Response.json({
      success: true,
      state: state,
      decisions: decisions.slice(-50), // Last 50 decisions
      safetyEvents: safetyEvents.slice(-20), // Last 20 safety events
      lastUpdate: state.last_update || null
    });
  } catch (error) {
    return Response.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}
