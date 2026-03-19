#!/usr/bin/env python3
"""
Script de Migração de Storage

Permite migrar dados entre diferentes backends:
- Cloudflare → Local (quando migrar para Raspberry Pi)
- Local → Cloudflare (se quiser voltar)

Uso:
    # Cloudflare para Local
    python scripts/migrate_storage.py --from cloudflare --to local

    # Local para Cloudflare
    python scripts/migrate_storage.py --from local --to cloudflare

    # Apenas exportar estado
    python scripts/migrate_storage.py --from cloudflare --to local --only-state
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage import get_storage, LocalStorage, CloudflareStorage
from src.storage.base import BotState, Trade

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def migrate_state(source, target):
    """Migra estado do bot."""
    logger.info("Migrating bot state...")

    state_data = source.load_state("bot")
    if state_data:
        target.save_state("bot", state_data)
        logger.info(f"  State migrated: capital=${state_data.get('capital', 0):.2f}")
    else:
        logger.warning("  No state found to migrate")


def migrate_trades(source, target, limit=10000):
    """Migra histórico de trades."""
    logger.info("Migrating trades...")

    trades = source.get_trades(limit=limit)
    migrated = 0

    for trade in trades:
        if target.save_trade(trade):
            migrated += 1

    logger.info(f"  Migrated {migrated} trades")


def migrate_models(source, target):
    """Migra modelos ML."""
    logger.info("Migrating ML models...")

    import tempfile

    models = ["regime_hmm.pkl", "strategy_xgb.pkl"]

    for model_name in models:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as tmp:
            tmp_path = tmp.name

        try:
            # Download do source
            if source.load_model(model_name, tmp_path):
                # Upload para target
                if target.save_model(model_name, tmp_path):
                    logger.info(f"  Migrated {model_name}")
                else:
                    logger.warning(f"  Failed to save {model_name} to target")
            else:
                logger.warning(f"  Model {model_name} not found in source")
        finally:
            # Limpar temp
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


def migrate_performance(source, target, days=365):
    """Migra histórico de performance."""
    logger.info("Migrating performance history...")

    history = source.get_performance_history(days=days)
    migrated = 0

    for record in history:
        date = record.get("date", "")
        if date and target.save_daily_performance(date, record):
            migrated += 1

    logger.info(f"  Migrated {migrated} performance records")


def get_backend(name: str):
    """Obtém backend pelo nome."""
    if name == "local":
        return LocalStorage()
    elif name == "cloudflare":
        storage = CloudflareStorage()
        if not storage.is_configured():
            logger.error("Cloudflare not configured. Set CF_* environment variables.")
            sys.exit(1)
        return storage
    else:
        logger.error(f"Unknown backend: {name}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Migrate storage between backends")
    parser.add_argument("--from", dest="source", required=True,
                       choices=["local", "cloudflare"],
                       help="Source backend")
    parser.add_argument("--to", dest="target", required=True,
                       choices=["local", "cloudflare"],
                       help="Target backend")
    parser.add_argument("--only-state", action="store_true",
                       help="Only migrate bot state")
    parser.add_argument("--only-trades", action="store_true",
                       help="Only migrate trades")
    parser.add_argument("--only-models", action="store_true",
                       help="Only migrate ML models")
    parser.add_argument("--trade-limit", type=int, default=10000,
                       help="Max trades to migrate")

    args = parser.parse_args()

    if args.source == args.target:
        logger.error("Source and target cannot be the same")
        sys.exit(1)

    logger.info(f"Migrating from {args.source} to {args.target}")
    logger.info("=" * 50)

    # Obter backends
    source = get_backend(args.source)
    target = get_backend(args.target)

    # Inicializar target
    target.init()

    # Determinar o que migrar
    migrate_all = not (args.only_state or args.only_trades or args.only_models)

    # Migrar
    if migrate_all or args.only_state:
        migrate_state(source, target)

    if migrate_all or args.only_trades:
        migrate_trades(source, target, limit=args.trade_limit)

    if migrate_all or args.only_models:
        migrate_models(source, target)

    if migrate_all:
        migrate_performance(source, target)

    logger.info("=" * 50)
    logger.info("Migration completed!")
    logger.info(f"Data now available in {args.target} backend")


if __name__ == "__main__":
    main()
