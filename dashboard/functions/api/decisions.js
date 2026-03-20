// Decision log endpoint - shows why bot made each decision

export async function onRequestGet(context) {
  const { env, request } = context;

  try {
    const url = new URL(request.url);
    const limit = parseInt(url.searchParams.get('limit') || '50');
    const asset = url.searchParams.get('asset');
    const type = url.searchParams.get('type'); // entry, exit, skip, hold

    // Get decision log from KV
    const decisionsData = await env.TRADING_KV.get('decision_log');

    if (!decisionsData) {
      return Response.json({
        success: true,
        decisions: [],
        message: 'No decisions logged yet'
      });
    }

    let decisions = JSON.parse(decisionsData);

    // Filter by asset if specified
    if (asset) {
      decisions = decisions.filter(d => d.asset === asset);
    }

    // Filter by type if specified
    if (type) {
      decisions = decisions.filter(d => d.type === type);
    }

    // Sort by timestamp descending
    decisions.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    // Apply limit
    decisions = decisions.slice(0, limit);

    // Get summary stats
    const stats = {
      total: decisions.length,
      entries: decisions.filter(d => d.type === 'entry').length,
      exits: decisions.filter(d => d.type === 'exit').length,
      skips: decisions.filter(d => d.type === 'skip').length,
      holds: decisions.filter(d => d.type === 'hold').length
    };

    return Response.json({
      success: true,
      decisions: decisions,
      stats: stats
    });
  } catch (error) {
    return Response.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}

// POST endpoint to add a decision (called by trading bot)
export async function onRequestPost(context) {
  const { env, request } = context;

  try {
    const decision = await request.json();

    // Validate required fields
    if (!decision.type || !decision.asset || !decision.timestamp) {
      return Response.json(
        { success: false, error: 'Missing required fields: type, asset, timestamp' },
        { status: 400 }
      );
    }

    // Get existing decisions
    const decisionsData = await env.TRADING_KV.get('decision_log');
    let decisions = decisionsData ? JSON.parse(decisionsData) : [];

    // Add new decision
    decisions.push({
      id: crypto.randomUUID(),
      ...decision,
      logged_at: new Date().toISOString()
    });

    // Keep only last 500 decisions
    if (decisions.length > 500) {
      decisions = decisions.slice(-500);
    }

    // Save back to KV
    await env.TRADING_KV.put('decision_log', JSON.stringify(decisions));

    return Response.json({ success: true, id: decisions[decisions.length - 1].id });
  } catch (error) {
    return Response.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}
