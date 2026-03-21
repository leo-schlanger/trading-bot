# Intelligent Trading Bot for Drift Protocol

Bot de trading automatizado com Machine Learning para detecção de regimes de mercado, seleção dinâmica de estratégias e detecção de armadilhas de mercado.

**Target:** Drift Protocol (Solana Perpetuals DEX)
**Capital:** $500 USD
**Timeframe:** 4h
**Mode:** Paper Trading (Live ready)

## Features

- **Detecção de Regime**: Classifica mercado em Bull/Bear/Sideways/Correction usando HMM + regras
- **Seleção de Estratégia**: XGBoost escolhe a melhor estratégia para o regime atual
- **Detecção de Armadilhas**: Sistema adaptativo detecta bull traps, bear traps, fake breakouts, divergências
- **Sinais LONG/SHORT**: Opera em ambas as direções conforme o regime
- **Gestão de Risco**: Position sizing com Kelly Criterion e limites por regime
- **Circuit Breakers**: Proteções automáticas (max drawdown, consecutive losses, etc)
- **Notificações**: Alertas via Telegram
- **Paper Trading**: Full position lifecycle with P&L tracking
- **Dashboard**: Real-time web dashboard with authentication (Cloudflare Pages)
- **Multi-Deploy**: GitHub Actions, Docker, Raspberry Pi, Oracle Cloud

## Quick Start

```bash
# Clone
git clone https://github.com/leo-schlanger/trading-bot.git
cd trading-bot

# Dependencies
pip install -r requirements.txt

# Download data
python scripts/download_recent_data.py --symbol BTC --bars 500
python scripts/download_recent_data.py --symbol ETH --bars 500

# Run paper trading
python run_trading_cycle.py --mode paper --symbols BTC ETH
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TRADING CYCLE (4h)                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Download Data (Pyth Network / Drift API)               │
│              ↓                                              │
│  2. Regime Detection (HMM + Rules)                         │
│     → BULL / BEAR / SIDEWAYS / CORRECTION                  │
│              ↓                                              │
│  3. Signal Generation (Multi-indicator)                    │
│     → EMA, MACD, RSI, Supertrend, ADX, Bollinger           │
│              ↓                                              │
│  4. Trap Detection (Adaptive)                              │
│     → Bull trap, Bear trap, Fake breakout, Divergence      │
│              ↓                                              │
│  5. Risk Management                                        │
│     → Position size, Stop loss, Take profit                │
│              ↓                                              │
│  6. Check Open Positions (SL/TP)                           │
│              ↓                                              │
│  7. Execute (Paper / Live)                                 │
│              ↓                                              │
│  8. Notify (Telegram)                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Estratégias Disponíveis

| Estratégia | Tipo | Melhor Regime |
|------------|------|---------------|
| EMA Cross | Trend | Bull |
| RSI Reversal | Mean Reversion | Sideways |
| Supertrend | Trend Following | Bull/Bear |
| Hull MA | Trend | Bull |
| Keltner Squeeze | Breakout | Sideways→Trend |
| Williams %R | Reversal | Sideways |
| Donchian Breakout | Breakout | Bull |
| Momentum | Trend | Bull |

## Trap Detection

O sistema detecta automaticamente:

| Armadilha | Descrição | Ação |
|-----------|-----------|------|
| Bull Trap | Falso rompimento de resistência | Evita LONG |
| Bear Trap | Falso rompimento de suporte | Evita SHORT |
| Fake Breakout | Rompimento sem volume | Evita entrada |
| Bearish Divergence | Preço sobe, RSI cai | Evita LONG |
| Bullish Divergence | Preço cai, RSI sobe | Evita SHORT |
| Exhaustion | Volume extremo + reversão | Sinal de reversão |
| Stop Hunt | Wick longo + reversão | Armadilha |

## Risk Management

| Regime | Position Size | Stop (ATR) | Target (ATR) |
|--------|--------------|------------|--------------|
| Bull | 80% | 3.0x | 4.5x |
| Bear | 50% | 2.0x | 3.0x |
| Sideways | 60% | 1.5x | 2.0x |
| Correction | 30% | 1.5x | 2.0x |

## Safety Controls

- **Max Consecutive Losses**: Pausa 24h após 3 losses seguidos
- **Daily Loss Limit**: Para se perder 5% no dia ($25)
- **Max Drawdown**: Para tudo se drawdown > 20% ($100)
- **High Volatility**: Reduz posição 50% se ATR > 2x média
- **Regime Change**: Pausa 2 candles após mudança de regime

## Project Structure

```
├── src/
│   ├── ml/                 # Machine Learning
│   │   ├── regime_detector.py    # HMM + Rules
│   │   ├── strategy_selector.py  # XGBoost
│   │   ├── features.py
│   │   └── validation.py
│   ├── signals/            # Signal Generation
│   │   ├── regime_signals.py     # Multi-indicator signals
│   │   └── trap_detector.py      # Trap detection
│   ├── optimization/       # Risk Management
│   │   ├── risk_manager.py
│   │   └── param_optimizer.py
│   ├── bot/               # Core Engine
│   │   ├── intelligent_engine.py
│   │   └── safety_controls.py
│   ├── storage/           # Data Persistence
│   │   ├── local.py       # SQLite + files
│   │   └── cloudflare.py  # KV + D1 + R2
│   └── notifications/     # Telegram
├── strategies/            # Trading Strategies
├── training/              # ML Training Pipeline
├── scripts/               # Utilities
├── config/                # Configuration
├── deploy/                # Deployment Options
│   ├── cloudflare/
│   ├── selfhosted/
│   ├── docker/
│   └── oracle/
└── .github/workflows/     # GitHub Actions
```

## Deployment Options

| Option | Cost | Frequency | Best For |
|--------|------|-----------|----------|
| GitHub Actions | $0 | Every 4h | Paper trading |
| Raspberry Pi | $50 once | Any | Self-hosted |
| Docker | Varies | Any | Flexibility |
| Oracle Cloud | $0 | Any | Free VPS |

See [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md) for detailed setup.

## Configuration

### Environment Variables

```bash
# Trading mode
TRADING_MODE=paper  # paper, live, backtest

# Telegram notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Cloudflare (optional)
CF_ACCOUNT_ID=your_account_id
CF_API_TOKEN=your_api_token
CF_KV_NAMESPACE_ID=your_kv_id
```

### Bot Config (config/bot_config.yaml)

```yaml
trading:
  initial_capital: 500
  assets: ["BTC", "ETH"]
  timeframe: "4h"

risk:
  max_position_pct: 0.95
  risk_per_trade_pct: 0.02
  max_daily_loss_pct: 0.05
  max_drawdown_pct: 0.20

safety:
  max_consecutive_losses: 3
  pause_after_losses_hours: 24
```

## Data Sources

| Source | Priority | Type |
|--------|----------|------|
| Pyth Network | 1 | Oracle (Drift's source) |
| Drift API | 2 | Direct from DEX |
| Birdeye | 3 | Solana aggregator |
| CryptoCompare | 4 | Fallback |

## Requirements

- Python 3.11+
- See `requirements.txt` for packages

## Dashboard

Web dashboard for real-time monitoring at `bot.leoschlanger.com`:

- **Stack**: React + Vite + Tailwind + shadcn/ui
- **Auth**: Password protected (SHA-256 hash)
- **Features**:
  - Real-time capital and PnL tracking
  - Open positions with entry/SL/TP
  - Current regime and signals per asset
  - Trade history with P&L per trade
  - Decision log with reasoning
  - Trap detection warnings
  - Performance metrics (win rate, profit factor)

See `dashboard/DEPLOY.md` for deployment instructions.

## Current Status

- [x] Regime detection (HMM + rules)
- [x] Signal generation (LONG/SHORT)
- [x] Trap detection (adaptive)
- [x] Risk management
- [x] Safety controls
- [x] GitHub Actions automation
- [x] Paper trading with P&L tracking
- [x] Web dashboard
- [x] Cloudflare KV persistence
- [x] ML models trained (HMM + XGBoost)
- [ ] Live trading (Drift SDK)
- [ ] Telegram notifications configured

## Disclaimer

This software is for educational purposes only. Trading cryptocurrencies involves substantial risk of loss. Use at your own risk.

## License

MIT
