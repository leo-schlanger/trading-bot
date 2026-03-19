"""
Notifications Module

Abstração para envio de notificações.
Atualmente suporta Telegram, mas pode ser expandido para Discord, Slack, etc.

Uso:
    from src.notifications import TelegramNotifier, notify_trade, notify_error

    # Via classe
    notifier = TelegramNotifier()
    notifier.send_trade_signal(symbol="BTC", action="BUY", ...)

    # Via funções de atalho
    notify_trade("BTC", "BUY", regime="BULL", strategy="Trend", confidence=0.8)
    notify_error("Falha na conexão")
    notify_status(capital=500, total_pnl=25)
"""

from .telegram import (
    TelegramNotifier,
    TelegramConfig,
    get_notifier,
    notify_trade,
    notify_error,
    notify_status,
)

__all__ = [
    "TelegramNotifier",
    "TelegramConfig",
    "get_notifier",
    "notify_trade",
    "notify_error",
    "notify_status",
]
