#!/usr/bin/env python3
"""
Trading Bot Daemon

Script simples para rodar o bot em qualquer servidor (Raspberry Pi, VPS, etc).
Pode ser usado com cron ou systemd timer.

Uso:
    # Uma execução
    python run_daemon.py

    # Com cron (a cada 4 horas)
    0 */4 * * * cd /home/pi/trading-bot && python run_daemon.py >> logs/daemon.log 2>&1

    # Com systemd timer (recomendado)
    Veja arquivos trading-bot.service e trading-bot.timer
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Adicionar diretório raiz ao path
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Configurar logging
log_dir = ROOT_DIR / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / f"daemon_{datetime.now().strftime('%Y%m%d')}.log")
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Executa um ciclo de trading."""
    logger.info("=" * 60)
    logger.info(f"Starting trading cycle at {datetime.now()}")
    logger.info("=" * 60)

    try:
        # Importar após configurar path
        from src.storage import get_storage
        from run_trading_cycle import TradingCycle

        # Obter storage (auto-detecta local vs cloudflare)
        storage = get_storage()
        logger.info(f"Using storage backend: {storage.get_backend_name()}")

        # Carregar estado
        state = storage.load_bot_state()
        logger.info(f"Capital: ${state.capital:.2f}")
        logger.info(f"Total PnL: ${state.total_pnl:.2f}")

        # Modo de trading
        mode = os.getenv("TRADING_MODE", "paper")
        logger.info(f"Mode: {mode}")

        # Executar ciclo
        cycle = TradingCycle(mode=mode)
        results = cycle.run(symbols=["BTC", "ETH"])

        # Log resultados
        for r in results:
            symbol = r["symbol"]
            action = r["analysis"]["action"]
            regime = r["analysis"]["regime"]
            logger.info(f"{symbol}: {action} (regime: {regime})")

        logger.info("Trading cycle completed successfully")

    except Exception as e:
        logger.error(f"Error in trading cycle: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
