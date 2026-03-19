"""
Signal Generation Module

Regime-based signal generation following 2026 best practices.
Includes adaptive trap detection for avoiding false signals.
"""

from .regime_signals import (
    RegimeSignalGenerator,
    TradeSignal,
    SignalDirection,
    SignalStrength,
)

from .trap_detector import (
    TrapDetector,
    TrapSignal,
    TrapType,
    MarketContext,
)

__all__ = [
    # Signal generation
    'RegimeSignalGenerator',
    'TradeSignal',
    'SignalDirection',
    'SignalStrength',
    # Trap detection
    'TrapDetector',
    'TrapSignal',
    'TrapType',
    'MarketContext',
]
