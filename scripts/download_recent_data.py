"""
Download dados recentes para análise.
Usado pelo GitHub Actions antes de cada ciclo.
"""

import argparse
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import requests
import time
import sys


def download_binance_klines(symbol: str, interval: str = "4h", bars: int = 500):
    """Download klines recentes da Binance."""

    symbol = symbol.upper() + "USDT"
    base_url = "https://api.binance.com/api/v3/klines"

    # Calcular timestamps
    end_time = int(datetime.now().timestamp() * 1000)

    # Calcular quantos dias precisamos baseado no intervalo
    interval_hours = {'1h': 1, '4h': 4, '1d': 24}.get(interval, 4)
    days_needed = (bars * interval_hours) / 24 + 1

    start_time = int((datetime.now() - timedelta(days=days_needed)).timestamp() * 1000)

    all_klines = []
    current_start = start_time

    print(f"Baixando {symbol} {interval}...")

    while current_start < end_time and len(all_klines) < bars:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "endTime": end_time,
            "limit": min(1000, bars - len(all_klines))
        }

        try:
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            klines = response.json()

            if not klines:
                break

            all_klines.extend(klines)
            current_start = klines[-1][0] + 1

            print(f"  {len(all_klines)}/{bars} candles", end="\r")
            time.sleep(0.2)

        except Exception as e:
            print(f"Erro: {e}")
            break

    if not all_klines:
        print("Nenhum dado baixado!")
        return None

    # Converter para DataFrame
    df = pd.DataFrame(all_klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

    # Pegar apenas as últimas N barras
    df = df.tail(bars)

    # Salvar
    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = output_dir / f"{symbol.replace('USDT', '')}_{interval}.csv"
    df.to_csv(filename)

    print(f"\nSalvo: {filename}")
    print(f"  Período: {df.index[0]} a {df.index[-1]}")
    print(f"  Candles: {len(df)}")

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC", help="Símbolo (BTC, ETH)")
    parser.add_argument("--timeframe", default="4h", help="Timeframe")
    parser.add_argument("--bars", type=int, default=500, help="Número de candles")

    args = parser.parse_args()

    download_binance_klines(args.symbol, args.timeframe, args.bars)


if __name__ == "__main__":
    main()
