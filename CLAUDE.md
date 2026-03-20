# Claude Context - Intelligent Trading Bot

> This file provides context for Claude AI sessions working on this project.
> Last updated: 2026-03-20 (Session 4)

## Project Overview

**Intelligent Trading Bot** for Drift Protocol (Solana perpetuals DEX) with:
- Machine Learning regime detection
- Adaptive trap detection
- Multi-strategy selection
- Automated execution via GitHub Actions

**Owner:** Leo Schlanger
**Capital:** $500 USD
**Status:** Paper Trading (Live ready pending Drift SDK integration)

## Current Architecture

```
Data (Pyth) → Regime Detection → Signal Generation → Trap Filter → Risk Management → Execute
```

### Key Components

| Component | File | Status |
|-----------|------|--------|
| Regime Detector | `src/ml/regime_detector.py` | ✅ Working (HMM trained) |
| Strategy Selector | `src/ml/strategy_selector.py` | ✅ Working (XGBoost trained) |
| Signal Generator | `src/signals/regime_signals.py` | ✅ Working |
| Trap Detector | `src/signals/trap_detector.py` | ✅ Working |
| Risk Manager | `src/optimization/risk_manager.py` | ✅ Working |
| Safety Controls | `src/bot/safety_controls.py` | ✅ Working |
| Trading Cycle | `run_trading_cycle.py` | ✅ Working |

### Data Flow

1. **Download Data**: `scripts/download_recent_data.py` → Pyth Network API
2. **Analyze**: `run_trading_cycle.py` → regime + signals + traps
3. **Execute**: Paper mode logs trades, Live mode (TODO) sends to Drift
4. **Persist**: State saved to `state/trading_state.json`

## Important Files

### Entry Points
- `run_trading_cycle.py` - Main 4h cycle (GitHub Actions)
- `run_intelligent_bot.py` - Backtest with ML
- `scripts/download_recent_data.py` - Data download

### Configuration
- `config/bot_config.yaml` - Main config
- `config/.env.example` - Environment template
- `.github/workflows/trading-bot-distributed.yml` - Active workflow

### ML (Trained)
- `training/generate_features.py` - Feature generation
- `training/train_regime_model.py` - HMM training
- `training/train_selector_model.py` - XGBoost training
- `models/regime_hmm.pkl` - HMM regime detector (4 states, 6000 samples)
- `models/strategy_xgb.pkl` - XGBoost strategy selector (98.9% accuracy)

## Regime System

```python
class MarketRegime(Enum):
    BULL = "bull"       # Uptrend, aggressive longs
    BEAR = "bear"       # Downtrend, aggressive shorts
    SIDEWAYS = "sideways"   # Range, mean reversion
    CORRECTION = "correction"  # Sharp drop, minimal trading
```

### Regime Config
| Regime | Long Bias | Position Size | Stop ATR | Target ATR |
|--------|-----------|---------------|----------|------------|
| BULL | 70% | 80% | 3.0x | 4.5x |
| BEAR | 30% | 50% | 2.0x | 3.0x |
| SIDEWAYS | 50% | 60% | 1.5x | 2.0x |
| CORRECTION | 40% | 30% | 1.5x | 2.0x |

## Signal Generation

Signals require 3+ confirmations from:
- EMA alignment (9/21/50)
- MACD crossover/momentum
- RSI levels
- Supertrend direction
- ADX trend strength
- Bollinger Band position
- Volume confirmation

## Trap Detection

Detects and filters:
- Bull traps (fake breakout up)
- Bear traps (fake breakdown)
- Divergences (RSI vs price)
- Exhaustion patterns
- Stop hunts
- Volume anomalies

**Confidence thresholds:**
- < 50%: No action
- 50-70%: Reduce confidence by 50%
- > 70%: Block signal

## Safety Controls

| Control | Threshold | Action |
|---------|-----------|--------|
| Consecutive Losses | 3 | Pause 24h |
| Daily Loss | 5% ($25) | Stop for day |
| Total Drawdown | 20% ($100) | Stop all |
| High Volatility | 2x ATR | Reduce position 50% |
| Regime Change | - | Pause 2 candles |

## Deployment

**Current:** GitHub Actions (every 4h UTC: 0,4,8,12,16,20)
**Workflow:** `.github/workflows/trading-bot-distributed.yml`

### Cloudflare
- KV: State storage (working - saves trading_state, trade_history, decision_log)
- D1: Trade history (not used)
- R2: ML models (empty)
- Pages: Dashboard (bot.leoschlanger.com)
- Secrets: All configured in GitHub

### Dashboard
- URL: bot.leoschlanger.com (Cloudflare Pages)
- Password: 041196 (SHA-256 hash in AUTH_PASSWORD_HASH)
- Stack: React + Vite + Tailwind + shadcn/ui
- Location: `dashboard/`
- Deploy: See `dashboard/DEPLOY.md`

## Pending Tasks

### High Priority
1. ~~**Train ML models**~~ - ✅ Done (HMM + XGBoost)
2. **Integrate Drift SDK** - For live trading

### Medium Priority
3. Configure Telegram notifications
4. Add unit tests
5. Implement incremental ML training (append new data, retrain)

### Low Priority
7. Add more data sources
8. Multi-timeframe analysis
9. On-chain metrics integration

## Common Commands

```bash
# Download data
python scripts/download_recent_data.py --symbol BTC --bars 500

# Run trading cycle
python run_trading_cycle.py --mode paper --symbols BTC ETH

# Run backtest
python run_intelligent_bot.py --data data/raw/BTC_4h.csv --mode backtest

# Train models (requires hmmlearn, xgboost)
python training/generate_features.py --data data/raw/BTC_4h.csv --output data/processed --asset BTC --type regime
python training/train_regime_model.py --features data/processed/BTC_regime_features.parquet --labels data/processed/BTC_regime_labels.parquet --output models/regime_hmm.pkl --validate
python training/train_selector_model.py --features data/processed/BTC_strategy_features.parquet --output models/strategy_xgb.pkl --validate --importance
```

## Code Patterns

### Adding New Trap Type
1. Add to `TrapType` enum in `src/signals/trap_detector.py`
2. Create `_detect_<trap_name>()` method
3. Add to `detect_all_traps()` method
4. Update `get_trap_summary()` if needed

### Adding New Indicator
1. Add to `src/indicators/technical.py`
2. Use in `RegimeSignalGenerator.calculate_indicators()`
3. Add to signal logic in `generate_signal()`

### Adding New Strategy
1. Create file in `strategies/`
2. Add to `StrategyType` enum in `src/ml/strategy_selector.py`
3. Add to `STRATEGY_NAMES` dict
4. Update `STRATEGY_REGIME_AFFINITY`

## Recent Changes (Session 4)

1. Fixed HMM feature mismatch bug in `regime_detector.py` - now uses same 5 features for training and inference
2. Downloaded 6000 candles (~2.7 years) historical data for BTC and ETH (4h timeframe)
3. Trained HMM regime detector (4 states, walk-forward validated)
4. Generated regime features (7 features) and strategy features (104 features)
5. Trained XGBoost strategy selector (98.9% accuracy, 27 walk-forward folds)
6. Saved models to `models/regime_hmm.pkl` and `models/strategy_xgb.pkl`
7. Saved API tokens to `config/.env.local` (not in git)

## Session 3

1. Deployed Dashboard to Cloudflare Pages (bot.leoschlanger.com)
2. Configured KV binding for production environment
3. Fixed `_load_state()` - added decision_log, last_signals, paper_trades initialization
4. Synced state with KV including decision_log and last_signals
5. Full project checkup completed

## Session 2

1. Fixed Cloudflare KV persistence (json.loads for read, text/plain for write)
2. Created Dashboard in `dashboard/` - React + shadcn/ui for Cloudflare Pages
3. Added decision_log and last_signals to trading state
4. Workflow now saves trade_history and decision_log to KV
5. Updated `run_trading_cycle.py` with `_log_decision()` method

## Session 1

1. Created `src/signals/trap_detector.py` - Adaptive trap detection
2. Integrated trap detection into `RegimeSignalGenerator`
3. Updated signal output to include trap warnings
4. Fixed duplicate workflow issue

## Known Issues

1. ~~**ML models not trained**~~ - ✅ Fixed (HMM + XGBoost trained)
2. **Live trading not implemented** - Drift SDK integration pending
3. **Warning messages** - `hmmlearn` and `xgboost` required for ML (pip install hmmlearn xgboost)

## Testing Commands

```bash
# Test imports
python -c "from src.signals import RegimeSignalGenerator, TrapDetector; print('OK')"

# Test with data
python -c "
import pandas as pd
from src.signals import RegimeSignalGenerator
df = pd.read_csv('data/raw/ETH_4h.csv', index_col=0, parse_dates=True)
gen = RegimeSignalGenerator()
signal = gen.generate_signal(df, 'bear')
print(f'{signal.direction.name}: {signal.confidence:.0%}')
print(f'Traps: {signal.traps_detected}')
"
```

## Contact

Repository: https://github.com/leo-schlanger/trading-bot
