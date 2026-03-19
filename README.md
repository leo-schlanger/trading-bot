# Intelligent Trading Bot

Bot de trading automatizado com Machine Learning para detecção de regimes de mercado e seleção dinâmica de estratégias.

## Features

- **Detecção de Regime**: Classifica mercado em Bull/Bear/Sideways/Correction usando HMM + regras
- **Seleção de Estratégia**: XGBoost escolhe a melhor estratégia para o regime atual
- **Gestão de Risco**: Position sizing com Kelly Criterion e limites por regime
- **Circuit Breakers**: Proteções automáticas (max drawdown, consecutive losses, etc)
- **Notificações**: Alertas via Telegram

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

## Setup

```bash
# Clone
git clone https://github.com/YOUR_USER/trading-bot.git
cd trading-bot

# Virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Dependencies
pip install -r requirements.txt

# Configuration
cp config/.env.example config/.env
# Edit .env with your settings
```

## Estrutura

```
├── src/
│   ├── ml/                 # Machine Learning
│   │   ├── regime_detector.py
│   │   ├── strategy_selector.py
│   │   ├── features.py
│   │   └── validation.py
│   ├── optimization/       # Risk Management
│   │   ├── risk_manager.py
│   │   └── param_optimizer.py
│   ├── bot/               # Core Engine
│   │   ├── intelligent_engine.py
│   │   └── safety_controls.py
│   ├── indicators/        # Technical Indicators
│   ├── storage/           # Data Persistence
│   └── notifications/     # Telegram
├── strategies/            # Trading Strategies
├── training/              # ML Training Pipeline
├── scripts/               # Utilities
├── config/                # Configuration
└── .github/workflows/     # GitHub Actions
```

## Usage

### Backtest

```bash
python run_intelligent_bot.py --data data/raw/BTC_4h.csv --mode backtest
```

### Paper Trading

```bash
python run_trading_cycle.py --mode paper
```

### Train Models

```bash
# Generate features
python training/generate_features.py --data data/raw/BTC_4h.csv --output data/processed

# Train regime detector
python training/train_regime_model.py --features data/processed/BTC_regime_features.parquet

# Train strategy selector
python training/train_selector_model.py --features data/processed/BTC_strategy_features.parquet
```

## Configuration

Edit `config/bot_config.yaml`:

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

## Environment Variables

```bash
# Trading mode
TRADING_MODE=paper  # paper, live, backtest

# Telegram notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Exchange (for live mode)
EXCHANGE_API_KEY=your_key
EXCHANGE_SECRET=your_secret
```

## Risk Management

| Regime | Position Size | Risk/Trade | Stop (ATR) |
|--------|--------------|------------|------------|
| Bull | 80% | 3% | 2.5x |
| Bear | 50% | 2% | 2.0x |
| Sideways | 60% | 2% | 1.5x |
| Correction | 30% | 1% | 1.5x |

## Safety Controls

- **Max Consecutive Losses**: Pausa após 3 losses seguidos
- **Daily Loss Limit**: Para se perder 5% no dia
- **Max Drawdown**: Para tudo se drawdown > 20%
- **High Volatility**: Reduz posição 50% se ATR > 2x média

## Requirements

- Python 3.11+
- See `requirements.txt` for packages

## Disclaimer

This software is for educational purposes only. Trading cryptocurrencies involves substantial risk of loss. Use at your own risk.

## License

MIT
