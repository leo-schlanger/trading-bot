"""
Storage Module

Abstraction layer for switching between storage backends without code changes.

Usage:
    from src.storage import get_storage

    # Auto-detect based on environment variables
    storage = get_storage()

    # Or force a specific backend
    storage = get_storage(backend="local")      # Self-hosted
    storage = get_storage(backend="cloudflare") # Serverless

The API is identical regardless of backend:
    storage.save_bot_state(state)
    storage.load_bot_state()
    storage.save_trade(trade)
    storage.get_trades()
    storage.save_model(name, path)
    storage.load_model(name, path)
"""

import os
import logging
from typing import Optional

from .base import StorageBackend, Trade, BotState
from .local import LocalStorage
from .cloudflare import CloudflareStorage

logger = logging.getLogger(__name__)

__all__ = [
    "get_storage",
    "StorageBackend",
    "Trade",
    "BotState",
    "LocalStorage",
    "CloudflareStorage",
]


def get_storage(backend: str = None, **kwargs) -> StorageBackend:
    """
    Factory to get appropriate storage backend.

    Args:
        backend: "local", "cloudflare", or None (auto-detect)
        **kwargs: Extra arguments for the backend

    Auto-detection:
        - If CF_ACCOUNT_ID is set → Cloudflare
        - Otherwise → Local

    Examples:
        # Auto-detect
        storage = get_storage()

        # Force local
        storage = get_storage(backend="local", data_dir="/path/to/data")

        # Force Cloudflare
        storage = get_storage(backend="cloudflare")
    """

    # Auto-detect if not specified
    if backend is None:
        if os.getenv("CF_ACCOUNT_ID") and os.getenv("CF_API_TOKEN"):
            backend = "cloudflare"
            logger.info("Auto-detected: Using Cloudflare storage")
        else:
            backend = "local"
            logger.info("Auto-detected: Using local storage")

    # Create appropriate backend
    if backend == "local":
        data_dir = kwargs.get("data_dir", os.getenv("BOT_DATA_DIR", "data"))
        storage = LocalStorage(data_dir=data_dir)

    elif backend == "cloudflare":
        storage = CloudflareStorage()

        if not storage.is_configured():
            logger.warning("Cloudflare not fully configured, falling back to local")
            data_dir = kwargs.get("data_dir", "data")
            storage = LocalStorage(data_dir=data_dir)

    else:
        raise ValueError(f"Unknown storage backend: {backend}")

    # Initialize
    storage.init()

    return storage


# Singleton for global usage (optional)
_global_storage: Optional[StorageBackend] = None


def get_global_storage() -> StorageBackend:
    """Get global storage instance."""
    global _global_storage
    if _global_storage is None:
        _global_storage = get_storage()
    return _global_storage


def set_global_storage(storage: StorageBackend):
    """Set global storage instance."""
    global _global_storage
    _global_storage = storage
