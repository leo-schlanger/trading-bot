"""
Estratégia: RSI Mean Reversion
Para mercados em range ou reversões em extremos.
"""

import pandas as pd
from typing import Optional
import sys
sys.path.append('..')

from src.backtest.engine import BaseStrategy
from src.indicators.technical import rsi, ema, atr, bollinger_bands


class RSIReversalStrategy(BaseStrategy):
    """
    RSI Mean Reversion com Bollinger Bands.

    Regras:
    - Long: RSI < oversold + preço toca banda inferior + fechamento acima
    - Short: RSI > overbought + preço toca banda superior + fechamento abaixo
    - Stop: Fora da banda oposta ou ATR
    - Take Profit: Banda do meio (SMA 20)
    """

    def __init__(self,
                 rsi_period: int = 7,  # Mais curto para scalp
                 rsi_oversold: float = 30,
                 rsi_overbought: float = 70,
                 bb_period: int = 20,
                 bb_std: float = 2.0,
                 atr_period: int = 14,
                 atr_sl_mult: float = 1.5,
                 use_trend_filter: bool = True,
                 trend_period: int = 100):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.use_trend_filter = use_trend_filter
        self.trend_period = trend_period

        self.warmup_period = max(bb_period, trend_period, 50) + 10

    def setup(self, data: pd.DataFrame):
        """Pré-calcular indicadores."""
        data['rsi'] = rsi(data['close'], self.rsi_period)

        bb_upper, bb_middle, bb_lower = bollinger_bands(
            data['close'],
            self.bb_period,
            self.bb_std
        )
        data['bb_upper'] = bb_upper
        data['bb_middle'] = bb_middle
        data['bb_lower'] = bb_lower

        data['atr'] = atr(data['high'], data['low'], data['close'], self.atr_period)

        if self.use_trend_filter:
            data['ema_trend'] = ema(data['close'], self.trend_period)

        # RSI momentum
        data['rsi_prev'] = data['rsi'].shift(1)

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        """Gerar sinal de trading."""
        if index < 2:
            return 0

        row = data.iloc[index]
        prev_row = data.iloc[index - 1]

        price = row['close']
        low = row['low']
        high = row['high']
        rsi_val = row['rsi']
        rsi_prev = row['rsi_prev']

        bb_lower = row['bb_lower']
        bb_upper = row['bb_upper']

        # Long: RSI oversold + toca banda inferior + RSI virando
        long_signal = (
            rsi_val < self.rsi_oversold and
            low <= bb_lower and
            price > bb_lower and  # Fechou acima
            rsi_val > rsi_prev  # RSI virando para cima
        )

        # Short: RSI overbought + toca banda superior + RSI virando
        short_signal = (
            rsi_val > self.rsi_overbought and
            high >= bb_upper and
            price < bb_upper and  # Fechou abaixo
            rsi_val < rsi_prev  # RSI virando para baixo
        )

        # Filtro de tendência (opcional) - não operar contra tendência forte
        if self.use_trend_filter:
            trend_ema = row['ema_trend']
            dist_from_trend = abs(price - trend_ema) / trend_ema

            # Se preço muito longe da média, pode ser tendência forte
            if dist_from_trend > 0.05:  # 5%
                if price > trend_ema and short_signal:
                    return 0  # Não shortar em tendência de alta forte
                if price < trend_ema and long_signal:
                    return 0  # Não comprar em tendência de baixa forte

        if long_signal:
            return 1
        elif short_signal:
            return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        """Stop loss baseado em ATR ou banda."""
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:  # Long
            # Stop abaixo da banda inferior
            bb_stop = row['bb_lower'] - (atr_val * 0.5)
            atr_stop = price - (atr_val * self.atr_sl_mult)
            return max(bb_stop, atr_stop)  # Usar o mais próximo
        else:  # Short
            # Stop acima da banda superior
            bb_stop = row['bb_upper'] + (atr_val * 0.5)
            atr_stop = price + (atr_val * self.atr_sl_mult)
            return min(bb_stop, atr_stop)  # Usar o mais próximo

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        """Take profit na banda do meio."""
        row = data.iloc[index]
        return row['bb_middle']
