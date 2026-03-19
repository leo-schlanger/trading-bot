"""
Signal Generation Module

Regime-based signal generation following 2026 best practices.
"""

from .regime_signals import (
    RegimeSignalGenerator,
    TradeSignal,
    SignalDirection,
    SignalStrength,
)

__all__ = [
    'RegimeSignalGenerator',
    'TradeSignal',
    'SignalDirection',
    'SignalStrength',
]
