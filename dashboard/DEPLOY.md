# Dashboard Deployment Guide

## Prerequisites

1. Cloudflare account with Pages enabled
2. KV namespace created (same as trading bot)
3. Node.js 18+ installed

## Local Development

```bash
cd dashboard
npm install
npm run dev
```

## Build for Production

```bash
npm run build
```

This creates a `dist/` folder with the production build.

## Deploy to Cloudflare Pages

### Option 1: CLI Deployment

```bash
# Install wrangler if not already
npm install -g wrangler

# Login to Cloudflare
wrangler login

# Deploy
wrangler pages deploy dist --project-name=trading-dashboard
```

### Option 2: GitHub Integration

1. Go to Cloudflare Dashboard > Pages
2. Create a new project
3. Connect your GitHub repository
4. Set build settings:
   - Build command: `npm run build`
   - Build output directory: `dist`
   - Root directory: `bots-drift/dashboard`

## Configure Environment

In Cloudflare Pages Dashboard:

1. Go to Settings > Environment Variables
2. Add production variables:

| Variable | Value |
|----------|-------|
| AUTH_PASSWORD_HASH | `8848feae3bf358fe9c769fb73027680a72ed0c46ff999ca8b736af46ceedb049` |

(This is SHA-256 hash of "041196")

3. Go to Settings > Functions
4. Add KV namespace binding:
   - Variable name: `TRADING_KV`
   - KV namespace: Select your trading bot KV namespace

## Custom Domain Setup

1. Go to Cloudflare Pages > Your Project > Custom Domains
2. Add custom domain: `bot.leoschlanger.com`
3. Configure DNS:
   - Add CNAME record: `bot` -> `trading-dashboard.pages.dev`
   - Or use Cloudflare DNS (automatic if domain is on Cloudflare)

## Verify Deployment

1. Visit your deployment URL
2. Enter password: `041196`
3. Verify data loads from KV

## Troubleshooting

### "No state data available"
- The trading bot hasn't run yet
- Check KV namespace binding is correct
- Verify KV has the `trading_state` key

### Authentication fails
- Verify AUTH_PASSWORD_HASH is set correctly
- Check KV binding for session storage

### API returns 500
- Check Function logs in Cloudflare Dashboard
- Verify KV namespace ID in wrangler.toml

## Password Hash Generation

To generate a new password hash:

```bash
echo -n "your-password" | sha256sum
```

Or in Python:
```python
import hashlib
hashlib.sha256("your-password".encode()).hexdigest()
```
