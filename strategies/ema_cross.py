"""
Estratégia: EMA Crossover
Simples e efetiva para trend following.
"""

import pandas as pd
from typing import Optional
import sys
sys.path.append('..')

from src.backtest.engine import BaseStrategy
from src.indicators.technical import ema, atr, rsi


class EMACrossStrategy(BaseStrategy):
    """
    EMA Crossover com filtro de tendência.

    Regras:
    - Long: EMA rápida cruza acima da EMA lenta + EMA 200 bullish
    - Short: EMA rápida cruza abaixo da EMA lenta + EMA 200 bearish
    - Stop: 2x ATR
    - Take Profit: 3x ATR (RR 1:1.5)
    """

    def __init__(self,
                 fast_period: int = 9,
                 slow_period: int = 21,
                 trend_period: int = 200,
                 atr_period: int = 14,
                 atr_sl_mult: float = 2.0,
                 atr_tp_mult: float = 3.0,
                 use_rsi_filter: bool = True,
                 rsi_period: int = 14):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trend_period = trend_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.use_rsi_filter = use_rsi_filter
        self.rsi_period = rsi_period

        self.warmup_period = max(trend_period, 50) + 10

    def setup(self, data: pd.DataFrame):
        """Pré-calcular indicadores."""
        data['ema_fast'] = ema(data['close'], self.fast_period)
        data['ema_slow'] = ema(data['close'], self.slow_period)
        data['ema_trend'] = ema(data['close'], self.trend_period)
        data['atr'] = atr(data['high'], data['low'], data['close'], self.atr_period)

        if self.use_rsi_filter:
            data['rsi'] = rsi(data['close'], self.rsi_period)

        # Crossover signals
        data['ema_cross'] = 0
        data.loc[
            (data['ema_fast'] > data['ema_slow']) &
            (data['ema_fast'].shift(1) <= data['ema_slow'].shift(1)),
            'ema_cross'
        ] = 1
        data.loc[
            (data['ema_fast'] < data['ema_slow']) &
            (data['ema_fast'].shift(1) >= data['ema_slow'].shift(1)),
            'ema_cross'
        ] = -1

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        """Gerar sinal de trading."""
        row = data.iloc[index]

        cross = row['ema_cross']
        if cross == 0:
            return 0

        price = row['close']
        trend_ema = row['ema_trend']

        # Filtro de tendência
        if cross > 0 and price < trend_ema:
            return 0  # Não comprar contra tendência
        if cross < 0 and price > trend_ema:
            return 0  # Não vender contra tendência

        # Filtro RSI (evitar extremos)
        if self.use_rsi_filter:
            rsi_val = row['rsi']
            if cross > 0 and rsi_val > 70:
                return 0  # Overbought
            if cross < 0 and rsi_val < 30:
                return 0  # Oversold

        return cross

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        """Stop loss baseado em ATR."""
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:  # Long
            return price - (atr_val * self.atr_sl_mult)
        else:  # Short
            return price + (atr_val * self.atr_sl_mult)

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        """Take profit baseado em ATR."""
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:  # Long
            return price + (atr_val * self.atr_tp_mult)
        else:  # Short
            return price - (atr_val * self.atr_tp_mult)
