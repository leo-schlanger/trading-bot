// Authentication middleware for all API routes

export async function onRequest(context) {
  const { request, env, next } = context;

  // Skip auth check for the auth endpoint itself
  const url = new URL(request.url);
  if (url.pathname === '/api/auth') {
    return next();
  }

  // Get token from Authorization header
  const authHeader = request.headers.get('Authorization');
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return Response.json(
      { error: 'Missing or invalid authorization header' },
      { status: 401 }
    );
  }

  const token = authHeader.replace('Bearer ', '');

  try {
    // Validate token in KV
    const sessionData = await env.TRADING_KV.get(`session:${token}`);

    if (!sessionData) {
      return Response.json(
        { error: 'Invalid or expired session' },
        { status: 401 }
      );
    }

    const session = JSON.parse(sessionData);

    if (!session.valid) {
      return Response.json(
        { error: 'Session invalidated' },
        { status: 401 }
      );
    }

    // Session valid, continue to endpoint
    return next();
  } catch (error) {
    return Response.json(
      { error: 'Authentication error' },
      { status: 500 }
    );
  }
}
