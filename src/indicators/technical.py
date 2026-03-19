"""
Indicadores técnicos otimizados para backtest.
Usa numpy para performance máxima.
"""

import numpy as np
import pandas as pd
from typing import Tuple


def sma(data: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return data.rolling(window=period).mean()


def ema(data: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return data.ewm(span=period, adjust=False).mean()


def rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index.
    Otimizado para evitar divisão por zero.
    """
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.inf)
    rsi_values = 100 - (100 / (1 + rs))

    return rsi_values


def macd(data: pd.Series,
         fast: int = 12,
         slow: int = 26,
         signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD - Moving Average Convergence Divergence.
    Retorna: (macd_line, signal_line, histogram)
    """
    ema_fast = ema(data, fast)
    ema_slow = ema(data, slow)

    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def bollinger_bands(data: pd.Series,
                    period: int = 20,
                    std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands.
    Retorna: (upper_band, middle_band, lower_band)
    """
    middle = sma(data, period)
    std = data.rolling(window=period).std()

    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)

    return upper, middle, lower


def atr(high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14) -> pd.Series:
    """
    Average True Range - para stops dinâmicos.
    """
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    return true_range.ewm(span=period, adjust=False).mean()


def fisher_transform(high: pd.Series,
                     low: pd.Series,
                     period: int = 10) -> Tuple[pd.Series, pd.Series]:
    """
    Fisher Transform - alternativa mais limpa ao RSI.
    Retorna: (fisher_line, trigger_line)
    """
    hl2 = (high + low) / 2

    highest = hl2.rolling(window=period).max()
    lowest = hl2.rolling(window=period).min()

    # Normalizar entre -1 e 1
    raw = 2 * ((hl2 - lowest) / (highest - lowest + 1e-10)) - 1
    raw = raw.clip(-0.999, 0.999)  # Evitar infinitos no log

    # Suavizar
    smooth = raw.ewm(span=5, adjust=False).mean()

    # Fisher Transform
    fisher = 0.5 * np.log((1 + smooth) / (1 - smooth))
    fisher = fisher.ewm(span=3, adjust=False).mean()

    trigger = fisher.shift(1)

    return fisher, trigger


def vwap(high: pd.Series,
         low: pd.Series,
         close: pd.Series,
         volume: pd.Series) -> pd.Series:
    """
    Volume Weighted Average Price.
    Reset diário para intraday (assumindo index é datetime).
    """
    typical_price = (high + low + close) / 3
    tp_volume = typical_price * volume

    # VWAP cumulativo
    cumulative_tp_vol = tp_volume.cumsum()
    cumulative_vol = volume.cumsum()

    return cumulative_tp_vol / cumulative_vol


def ema_crossover(data: pd.Series, fast: int = 9, slow: int = 21) -> pd.Series:
    """
    Sinal de crossover EMA.
    Retorna: 1 (bullish cross), -1 (bearish cross), 0 (sem sinal)
    """
    ema_fast = ema(data, fast)
    ema_slow = ema(data, slow)

    # Posição atual e anterior
    position = (ema_fast > ema_slow).astype(int)
    position_prev = position.shift(1)

    # Crossover
    signal = position - position_prev

    return signal


def supertrend(high: pd.Series,
               low: pd.Series,
               close: pd.Series,
               period: int = 10,
               multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    """
    Supertrend indicator.
    Retorna: (supertrend_line, direction)
    direction: 1 = uptrend, -1 = downtrend
    """
    atr_val = atr(high, low, close, period)
    hl2 = (high + low) / 2

    upper_band = hl2 + (multiplier * atr_val)
    lower_band = hl2 - (multiplier * atr_val)

    supertrend = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=int)

    supertrend.iloc[0] = upper_band.iloc[0]
    direction.iloc[0] = 1

    for i in range(1, len(close)):
        if close.iloc[i] > supertrend.iloc[i-1]:
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1
        else:
            supertrend.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1

        # Ajustar bandas
        if direction.iloc[i] == 1 and lower_band.iloc[i] < supertrend.iloc[i-1]:
            supertrend.iloc[i] = supertrend.iloc[i-1]
        if direction.iloc[i] == -1 and upper_band.iloc[i] > supertrend.iloc[i-1]:
            supertrend.iloc[i] = supertrend.iloc[i-1]

    return supertrend, direction


def adx(high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Average Directional Index - measures trend strength.

    ADX values interpretation:
    - 0-20: Weak/No trend (sideways market)
    - 20-25: Trend developing
    - 25-50: Strong trend
    - 50-75: Very strong trend
    - 75-100: Extremely strong trend

    Returns: (adx, plus_di, minus_di)
    - adx: The ADX line (trend strength, not direction)
    - plus_di: +DI (bullish directional indicator)
    - minus_di: -DI (bearish directional indicator)
    """
    # Calculate True Range
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Calculate Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    # +DM and -DM
    plus_dm = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    # Smoothed values using Wilder's smoothing (similar to EMA)
    atr_smooth = true_range.ewm(span=period, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(span=period, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(span=period, adjust=False).mean()

    # Calculate +DI and -DI
    plus_di = 100 * (plus_dm_smooth / atr_smooth.replace(0, np.inf))
    minus_di = 100 * (minus_dm_smooth / atr_smooth.replace(0, np.inf))

    # Calculate DX
    di_diff = abs(plus_di - minus_di)
    di_sum = plus_di + minus_di
    dx = 100 * (di_diff / di_sum.replace(0, np.inf))

    # Calculate ADX (smoothed DX)
    adx_line = dx.ewm(span=period, adjust=False).mean()

    return adx_line, plus_di, minus_di


def roc(data: pd.Series, period: int = 10) -> pd.Series:
    """
    Rate of Change - momentum indicator.

    ROC = ((Current Price - Price n periods ago) / Price n periods ago) * 100

    Returns percentage change over the period.
    """
    prev_data = data.shift(period)
    return ((data - prev_data) / prev_data.replace(0, np.inf)) * 100


def donchian_channels(high: pd.Series,
                      low: pd.Series,
                      period: int = 20) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Donchian Channels - breakout indicator.

    Returns: (upper_channel, middle_channel, lower_channel)
    - upper: Highest high over period
    - lower: Lowest low over period
    - middle: Average of upper and lower
    """
    upper = high.rolling(window=period).max()
    lower = low.rolling(window=period).min()
    middle = (upper + lower) / 2

    return upper, middle, lower


def keltner_channels(high: pd.Series,
                     low: pd.Series,
                     close: pd.Series,
                     ema_period: int = 20,
                     atr_period: int = 10,
                     multiplier: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Keltner Channels - volatility-based envelope.

    Returns: (upper_channel, middle_channel, lower_channel)
    """
    middle = ema(close, ema_period)
    atr_val = atr(high, low, close, atr_period)

    upper = middle + (multiplier * atr_val)
    lower = middle - (multiplier * atr_val)

    return upper, middle, lower


def williams_r(high: pd.Series,
               low: pd.Series,
               close: pd.Series,
               period: int = 14) -> pd.Series:
    """
    Williams %R - momentum indicator similar to stochastic.

    Range: -100 to 0
    - Above -20: Overbought
    - Below -80: Oversold
    """
    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()

    wr = -100 * ((highest_high - close) / (highest_high - lowest_low).replace(0, np.inf))

    return wr


def hull_ma(data: pd.Series, period: int = 16) -> pd.Series:
    """
    Hull Moving Average - faster, smoother MA.

    HMA = WMA(2*WMA(n/2) - WMA(n)), sqrt(n))
    Using EMA as approximation for WMA.
    """
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))

    wma_half = ema(data, half_period)
    wma_full = ema(data, period)

    raw_hma = 2 * wma_half - wma_full
    hma = ema(raw_hma, sqrt_period)

    return hma
