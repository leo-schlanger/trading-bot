"""
Estratégias Avançadas baseadas em pesquisa.
Fontes: QuantifiedStrategies, TradingView, PyQuantLab
"""

import pandas as pd
import numpy as np
from typing import Optional
import sys
sys.path.insert(0, '..')

from src.backtest.engine import BaseStrategy
from src.indicators.technical import ema, sma, rsi, atr, bollinger_bands


# ============================================================================
# INDICADORES ADICIONAIS
# ============================================================================

def hull_ma(data: pd.Series, period: int = 14) -> pd.Series:
    """
    Hull Moving Average - mais responsivo que EMA.
    HMA = WMA(2*WMA(n/2) − WMA(n)), sqrt(n))
    """
    half_period = max(1, period // 2)
    sqrt_period = max(1, int(np.sqrt(period)))

    wma_half = data.rolling(window=half_period).apply(
        lambda x: np.sum(x * np.arange(1, len(x)+1)) / np.sum(np.arange(1, len(x)+1)),
        raw=True
    )
    wma_full = data.rolling(window=period).apply(
        lambda x: np.sum(x * np.arange(1, len(x)+1)) / np.sum(np.arange(1, len(x)+1)),
        raw=True
    )

    raw_hma = 2 * wma_half - wma_full

    hma = raw_hma.rolling(window=sqrt_period).apply(
        lambda x: np.sum(x * np.arange(1, len(x)+1)) / np.sum(np.arange(1, len(x)+1)),
        raw=True
    )

    return hma


def keltner_channels(high: pd.Series, low: pd.Series, close: pd.Series,
                     ema_period: int = 20, atr_period: int = 10,
                     multiplier: float = 2.0):
    """Keltner Channels."""
    basis = ema(close, ema_period)
    atr_val = atr(high, low, close, atr_period)

    upper = basis + (multiplier * atr_val)
    lower = basis - (multiplier * atr_val)

    return upper, basis, lower


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series,
               period: int = 14) -> pd.Series:
    """Williams %R oscillator."""
    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()

    wr = -100 * (highest_high - close) / (highest_high - lowest_low + 1e-10)

    return wr


def donchian_channels(high: pd.Series, low: pd.Series,
                      period: int = 20):
    """Donchian Channels."""
    upper = high.rolling(window=period).max()
    lower = low.rolling(window=period).min()
    middle = (upper + lower) / 2

    return upper, middle, lower


def squeeze_indicator(bb_upper: pd.Series, bb_lower: pd.Series,
                      kc_upper: pd.Series, kc_lower: pd.Series) -> pd.Series:
    """
    Squeeze indicator - True quando BB está dentro de KC (baixa volatilidade).
    """
    squeeze = (bb_lower > kc_lower) & (bb_upper < kc_upper)
    return squeeze.astype(int)


# ============================================================================
# ESTRATÉGIA 1: Hull MA Crossover
# ============================================================================

class HullMACrossStrategy(BaseStrategy):
    """
    Hull Moving Average Crossover.
    HMA é mais responsivo que EMA, reduz lag.

    Backtest reportado: 68% retorno vs 14% buy&hold.
    Fonte: hullmovingaverage.com
    """

    def __init__(self,
                 fast_period: int = 9,
                 slow_period: int = 21,
                 atr_period: int = 14,
                 atr_sl_mult: float = 2.0,
                 atr_tp_mult: float = 3.0,
                 use_rsi_filter: bool = True):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.use_rsi_filter = use_rsi_filter

        self.warmup_period = max(slow_period * 2, 50)

    def setup(self, data: pd.DataFrame):
        data['hma_fast'] = hull_ma(data['close'], self.fast_period)
        data['hma_slow'] = hull_ma(data['close'], self.slow_period)
        data['atr'] = atr(data['high'], data['low'], data['close'], self.atr_period)

        if self.use_rsi_filter:
            data['rsi'] = rsi(data['close'], 14)

        # Direção do HMA (slope)
        data['hma_fast_slope'] = data['hma_fast'].diff()
        data['hma_slow_slope'] = data['hma_slow'].diff()

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        if index < 2:
            return 0

        row = data.iloc[index]
        prev = data.iloc[index - 1]

        hma_fast = row['hma_fast']
        hma_slow = row['hma_slow']
        hma_fast_prev = prev['hma_fast']
        hma_slow_prev = prev['hma_slow']

        # Crossover
        bullish_cross = (hma_fast > hma_slow) and (hma_fast_prev <= hma_slow_prev)
        bearish_cross = (hma_fast < hma_slow) and (hma_fast_prev >= hma_slow_prev)

        # Confirmar com slope
        if bullish_cross and row['hma_fast_slope'] > 0:
            if self.use_rsi_filter and row['rsi'] > 70:
                return 0
            return 1

        if bearish_cross and row['hma_fast_slope'] < 0:
            if self.use_rsi_filter and row['rsi'] < 30:
                return 0
            return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:
            return price - (atr_val * self.atr_sl_mult)
        else:
            return price + (atr_val * self.atr_sl_mult)

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:
            return price + (atr_val * self.atr_tp_mult)
        else:
            return price - (atr_val * self.atr_tp_mult)


# ============================================================================
# ESTRATÉGIA 2: Keltner Squeeze Breakout
# ============================================================================

class KeltnerSqueezeStrategy(BaseStrategy):
    """
    Keltner Channel + Bollinger Band Squeeze.
    Identifica compressão de volatilidade e captura breakouts.

    Win rate reportado: 77% (QuantifiedStrategies)
    """

    def __init__(self,
                 bb_period: int = 20,
                 bb_std: float = 2.0,
                 kc_period: int = 20,
                 kc_atr_period: int = 10,
                 kc_mult: float = 1.5,
                 squeeze_lookback: int = 6,  # Mínimo de barras em squeeze
                 atr_period: int = 14,
                 atr_sl_mult: float = 2.0,
                 atr_tp_mult: float = 3.0):

        self.bb_period = bb_period
        self.bb_std = bb_std
        self.kc_period = kc_period
        self.kc_atr_period = kc_atr_period
        self.kc_mult = kc_mult
        self.squeeze_lookback = squeeze_lookback
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

        self.warmup_period = max(bb_period, kc_period, 50) + squeeze_lookback

    def setup(self, data: pd.DataFrame):
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = bollinger_bands(
            data['close'], self.bb_period, self.bb_std
        )
        data['bb_upper'] = bb_upper
        data['bb_middle'] = bb_middle
        data['bb_lower'] = bb_lower

        # Keltner Channels
        kc_upper, kc_middle, kc_lower = keltner_channels(
            data['high'], data['low'], data['close'],
            self.kc_period, self.kc_atr_period, self.kc_mult
        )
        data['kc_upper'] = kc_upper
        data['kc_middle'] = kc_middle
        data['kc_lower'] = kc_lower

        # Squeeze: BB dentro de KC
        data['squeeze'] = squeeze_indicator(bb_upper, bb_lower, kc_upper, kc_lower)

        # Contar barras consecutivas em squeeze
        data['squeeze_count'] = data['squeeze'].groupby(
            (data['squeeze'] != data['squeeze'].shift()).cumsum()
        ).cumcount() + 1

        # ATR para stops
        data['atr'] = atr(data['high'], data['low'], data['close'], self.atr_period)

        # Momentum (para direção do breakout)
        data['momentum'] = data['close'] - data['close'].shift(self.squeeze_lookback)

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        if index < self.squeeze_lookback:
            return 0

        row = data.iloc[index]
        prev = data.iloc[index - 1]

        # Verificar se estava em squeeze e agora saiu
        was_squeezed = prev['squeeze'] == 1 and prev['squeeze_count'] >= self.squeeze_lookback
        squeeze_released = row['squeeze'] == 0

        if not (was_squeezed and squeeze_released):
            return 0

        price = row['close']
        momentum = row['momentum']

        # Breakout bullish: preço acima da banda superior de Keltner
        if price > row['kc_upper'] and momentum > 0:
            return 1

        # Breakout bearish: preço abaixo da banda inferior de Keltner
        if price < row['kc_lower'] and momentum < 0:
            return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:
            return price - (atr_val * self.atr_sl_mult)
        else:
            return price + (atr_val * self.atr_sl_mult)

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:
            return price + (atr_val * self.atr_tp_mult)
        else:
            return price - (atr_val * self.atr_tp_mult)


# ============================================================================
# ESTRATÉGIA 3: Williams %R + RSI
# ============================================================================

class WilliamsRSIStrategy(BaseStrategy):
    """
    Williams %R combinado com RSI.
    Win rate reportado: 81% (QuantifiedStrategies)

    Melhor para mean reversion em oversold/overbought.
    """

    def __init__(self,
                 williams_period: int = 14,
                 rsi_period: int = 14,
                 oversold_wr: float = -80,
                 overbought_wr: float = -20,
                 oversold_rsi: float = 30,
                 overbought_rsi: float = 70,
                 ema_period: int = 9,
                 atr_period: int = 14,
                 atr_sl_mult: float = 1.5,
                 atr_tp_mult: float = 2.0):

        self.williams_period = williams_period
        self.rsi_period = rsi_period
        self.oversold_wr = oversold_wr
        self.overbought_wr = overbought_wr
        self.oversold_rsi = oversold_rsi
        self.overbought_rsi = overbought_rsi
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

        self.warmup_period = max(williams_period, rsi_period, 50)

    def setup(self, data: pd.DataFrame):
        data['williams_r'] = williams_r(
            data['high'], data['low'], data['close'], self.williams_period
        )
        data['rsi'] = rsi(data['close'], self.rsi_period)
        data['ema'] = ema(data['close'], self.ema_period)
        data['atr'] = atr(data['high'], data['low'], data['close'], self.atr_period)

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        if index < 2:
            return 0

        row = data.iloc[index]
        prev = data.iloc[index - 1]

        wr = row['williams_r']
        rsi_val = row['rsi']
        price = row['close']
        ema_val = row['ema']

        # Buy: WR oversold + RSI oversold + preço cruzou acima da EMA
        buy_wr = wr < self.oversold_wr or prev['williams_r'] < self.oversold_wr
        buy_rsi = rsi_val < self.oversold_rsi + 10  # Dar margem
        buy_price = price > ema_val and data.iloc[index-1]['close'] <= data.iloc[index-1]['ema']

        if buy_wr and buy_rsi and buy_price:
            return 1

        # Sell: WR overbought + RSI overbought + preço cruzou abaixo da EMA
        sell_wr = wr > self.overbought_wr or prev['williams_r'] > self.overbought_wr
        sell_rsi = rsi_val > self.overbought_rsi - 10
        sell_price = price < ema_val and data.iloc[index-1]['close'] >= data.iloc[index-1]['ema']

        if sell_wr and sell_rsi and sell_price:
            return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:
            return price - (atr_val * self.atr_sl_mult)
        else:
            return price + (atr_val * self.atr_sl_mult)

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:
            return price + (atr_val * self.atr_tp_mult)
        else:
            return price - (atr_val * self.atr_tp_mult)


# ============================================================================
# ESTRATÉGIA 4: Donchian Breakout
# ============================================================================

class DonchianBreakoutStrategy(BaseStrategy):
    """
    Donchian Channel Breakout - estratégia clássica de trend following.
    Usado pelos Turtle Traders.

    Simples mas efetivo em mercados trending.
    """

    def __init__(self,
                 entry_period: int = 20,
                 exit_period: int = 10,
                 atr_period: int = 14,
                 atr_sl_mult: float = 2.0,
                 use_filter: bool = True,
                 filter_period: int = 50):

        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.use_filter = use_filter
        self.filter_period = filter_period

        self.warmup_period = max(entry_period, exit_period, filter_period, 50) + 10

    def setup(self, data: pd.DataFrame):
        # Canais de entrada (mais longos)
        entry_upper, entry_middle, entry_lower = donchian_channels(
            data['high'], data['low'], self.entry_period
        )
        data['entry_upper'] = entry_upper
        data['entry_lower'] = entry_lower

        # Canais de saída (mais curtos)
        exit_upper, exit_middle, exit_lower = donchian_channels(
            data['high'], data['low'], self.exit_period
        )
        data['exit_upper'] = exit_upper
        data['exit_lower'] = exit_lower

        data['atr'] = atr(data['high'], data['low'], data['close'], self.atr_period)

        if self.use_filter:
            data['trend_filter'] = ema(data['close'], self.filter_period)

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        if index < 2:
            return 0

        row = data.iloc[index]
        prev = data.iloc[index - 1]

        high = row['high']
        low = row['low']
        close = row['close']

        entry_upper = prev['entry_upper']  # Usar valor anterior para evitar lookahead
        entry_lower = prev['entry_lower']

        # Breakout para cima
        if high > entry_upper:
            if self.use_filter and close < row['trend_filter']:
                return 0  # Não comprar contra tendência de baixa
            return 1

        # Breakout para baixo
        if low < entry_lower:
            if self.use_filter and close > row['trend_filter']:
                return 0  # Não vender contra tendência de alta
            return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:
            # Stop no canal inferior de saída
            return max(row['exit_lower'], price - (atr_val * self.atr_sl_mult))
        else:
            return min(row['exit_upper'], price + (atr_val * self.atr_sl_mult))

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        # Sem take profit fixo - deixar o trend riding
        return None


# ============================================================================
# ESTRATÉGIA 5: Multi-Timeframe Momentum
# ============================================================================

class MomentumBreakoutStrategy(BaseStrategy):
    """
    Momentum Breakout com confirmação de volume.
    Baseado em pesquisa de stoic.ai e PyQuantLab.

    Sharpe reportado: ~1.2 com volatility filtering.
    """

    def __init__(self,
                 momentum_period: int = 14,
                 ema_fast: int = 8,
                 ema_slow: int = 21,
                 volume_ma_period: int = 20,
                 volume_threshold: float = 1.5,  # Volume > 1.5x média
                 atr_period: int = 14,
                 atr_sl_mult: float = 2.0,
                 atr_tp_mult: float = 3.5):

        self.momentum_period = momentum_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.volume_ma_period = volume_ma_period
        self.volume_threshold = volume_threshold
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

        self.warmup_period = max(momentum_period, ema_slow, volume_ma_period, 50)

    def setup(self, data: pd.DataFrame):
        # Momentum (ROC)
        data['momentum'] = data['close'].pct_change(self.momentum_period)

        # EMAs
        data['ema_fast'] = ema(data['close'], self.ema_fast)
        data['ema_slow'] = ema(data['close'], self.ema_slow)

        # Volume analysis
        data['volume_ma'] = data['volume'].rolling(window=self.volume_ma_period).mean()
        data['volume_ratio'] = data['volume'] / data['volume_ma']

        # ATR
        data['atr'] = atr(data['high'], data['low'], data['close'], self.atr_period)

        # Z-score do momentum (normalizado)
        data['momentum_ma'] = data['momentum'].rolling(window=self.momentum_period).mean()
        data['momentum_std'] = data['momentum'].rolling(window=self.momentum_period).std()
        data['momentum_zscore'] = (data['momentum'] - data['momentum_ma']) / (data['momentum_std'] + 1e-10)

    def generate_signal(self, data: pd.DataFrame, index: int) -> int:
        if index < 2:
            return 0

        row = data.iloc[index]
        prev = data.iloc[index - 1]

        momentum = row['momentum']
        zscore = row['momentum_zscore']
        volume_ratio = row['volume_ratio']
        ema_fast = row['ema_fast']
        ema_slow = row['ema_slow']
        price = row['close']

        # Condições de volume
        high_volume = volume_ratio > self.volume_threshold

        # Condições de tendência
        uptrend = ema_fast > ema_slow
        downtrend = ema_fast < ema_slow

        # Crossover de EMA
        bullish_cross = uptrend and (prev['ema_fast'] <= prev['ema_slow'])
        bearish_cross = downtrend and (prev['ema_fast'] >= prev['ema_slow'])

        # Long: Momentum positivo + tendência de alta + volume alto
        if bullish_cross and momentum > 0 and zscore > 0.5 and high_volume:
            return 1

        # Short: Momentum negativo + tendência de baixa + volume alto
        if bearish_cross and momentum < 0 and zscore < -0.5 and high_volume:
            return -1

        return 0

    def get_stop_loss(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:
            return price - (atr_val * self.atr_sl_mult)
        else:
            return price + (atr_val * self.atr_sl_mult)

    def get_take_profit(self, data: pd.DataFrame, index: int, signal: int) -> Optional[float]:
        row = data.iloc[index]
        atr_val = row['atr']
        price = row['close']

        if signal > 0:
            return price + (atr_val * self.atr_tp_mult)
        else:
            return price - (atr_val * self.atr_tp_mult)
