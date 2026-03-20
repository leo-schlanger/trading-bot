// Authentication endpoint

export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const body = await request.json();
    const password = body.password;

    // Hash the password
    const encoder = new TextEncoder();
    const data = encoder.encode(password);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

    // Compare with stored hash (set in Cloudflare env)
    const storedHash = env.AUTH_PASSWORD_HASH;

    if (hashHex === storedHash) {
      // Generate session token
      const token = crypto.randomUUID();

      // Store token in KV with 24h expiry
      await env.TRADING_KV.put(`session:${token}`, JSON.stringify({
        valid: true,
        created: Date.now()
      }), {
        expirationTtl: 86400
      });

      return Response.json({ success: true, token });
    } else {
      return Response.json({ success: false, error: 'Invalid password' }, { status: 401 });
    }
  } catch (error) {
    return Response.json({ success: false, error: error.message }, { status: 500 });
  }
}
