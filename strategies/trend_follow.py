"""
Estratégia: Trend Following Completa
Combina múltiplos indicadores para capturar tendências.
"""

import pandas as pd
import numpy as np
from typing import Optional
import sys
sys.path.append('..')

from src.backtest.engine import BaseStrategy
from src.indicators.technical import ema, atr, rsi, macd, supertrend


class TrendFollowStrategy(BaseStrategy):
    """
    Trend Following com múltipla confirmação.

    Regras de Entrada:
    - Long: Supertrend bullish + MACD positivo + EMA stack bullish
    - Short: Supertrend bearish + MACD negativo + EMA stack bearish

    Regras de Saída:
    - Trailing stop baseado em ATR
    - Ou reversão do Supertrend

    Esta é a estratégia mais robusta para capturar movimentos grandes.
    """

    def __init__(self,
                 # Supertrend
                 st_period: int = 10,
                 st_multiplier: float = 3.0,
                 # EMAs
                 ema_fast: int = 8,
                 ema_medium: int = 21,
                 ema_slow: int = 55,
                 # MACD
                 macd_fast: int = 12,
                 macd_slow: int = 26,
                 macd_signal: int = 9,
                 # ATR
                 atr_period: int = 14,
                 atr_sl_mult: float = 2.5,
                 atr_tp_mult: float = 4.0,  # RR 1:1.6
                 # RSI filter
                 use_rsi_filter: bool = True,
                 rsi_period: int = 14):

        self.st_period = st_period
        self.st_multiplier = st_multiplier
        self.ema_fast = ema_fast
        self.ema_medium = ema_medium
        self.ema_slow = ema_slow
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.use_rsi_filter = use_rsi_filter
        self.rsi_period = rsi_period

        self.warmup_period = max(ema_slow, macd_slow, st_period, 60) + 10

    def setup(self, data: pd.DataFrame):
        """Pré-calcular indicadores."""
        # EMAs
        data['ema_fast'] = ema(data['close'], self.ema_fast)
        data['ema_medium'] = ema(data['close'], self.ema_medium)
        data['ema_slow'] = ema(data['close'], self.ema_slow)

        # MACD
        macd_line, signal_line, histogram = macd(
            data['close'],
            self.macd_fast,
            self.macd_slow,
            self.macd_signal
        )
        data['macd'] = macd_line
        data['macd_signal'] = signal_line
        data['macd_hist'] = histogram

        # ATR
        data['atr'] = atr(data['high'], data['low'], data['close'], self.atr_period)

        # Supertrend
        st_line, st_direction = supertrend(
            data['high'],
            data['low'],
            data['close'],
            self.st_period,
            self.st_multiplier
        )
        data['supertrend'] = st_line
        data['st_direction'] = st_direction

        # RSI
        if self.use_rsi_filter:
            data['rsi'] = rsi(data['close'], self.rsi_period)

        # EMA Stack
        data['ema_stack_bull'] = (
            (data['ema_fast'] > data['ema_medium']) &
            (data['ema_medium'] > data['ema_slow'])
        ).astype(int)

        data['ema_stack_bear'] = (
            (data['ema_fast'] < data['ema_medium']) &
            (data['ema_medium'] < data['ema_slow'])
        ).astype(int)

        # Supertrend flip
        data['st_flip'] = data['st_direction'].diff()

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        """Gerar sinal de trading."""
        row = data.iloc[index]

        st_dir = row['st_direction']
        st_flip = row['st_flip']
        macd_hist = row['macd_hist']
        ema_bull = row['ema_stack_bull']
        ema_bear = row['ema_stack_bear']

        # Só entrar quando Supertrend flipa (novo sinal)
        if st_flip == 0:
            return 0

        # Long: Supertrend virou bullish
        if st_flip > 0:  # Mudou de -1 para 1
            # Confirmações
            macd_ok = macd_hist > 0
            ema_ok = ema_bull or (row['ema_fast'] > row['ema_medium'])

            if macd_ok and ema_ok:
                # Filtro RSI
                if self.use_rsi_filter:
                    rsi_val = row['rsi']
                    if rsi_val > 75:
                        return 0  # Muito overbought

                return 1

        # Short: Supertrend virou bearish
        elif st_flip < 0:  # Mudou de 1 para -1
            # Confirmações
            macd_ok = macd_hist < 0
            ema_ok = ema_bear or (row['ema_fast'] < row['ema_medium'])

            if macd_ok and ema_ok:
                # Filtro RSI
                if self.use_rsi_filter:
                    rsi_val = row['rsi']
                    if rsi_val < 25:
                        return 0  # Muito oversold

                return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        """Stop loss baseado em ATR."""
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        # Usar Supertrend como referência também
        st = row['supertrend']

        if signal > 0:  # Long
            atr_stop = price - (atr_val * self.atr_sl_mult)
            # Stop não pode ser acima do Supertrend
            return min(atr_stop, st - (atr_val * 0.5))
        else:  # Short
            atr_stop = price + (atr_val * self.atr_sl_mult)
            return max(atr_stop, st + (atr_val * 0.5))

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        """Take profit baseado em ATR."""
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:  # Long
            return price + (atr_val * self.atr_tp_mult)
        else:  # Short
            return price - (atr_val * self.atr_tp_mult)
