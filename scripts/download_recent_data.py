"""
Download recent market data for analysis.
Used by GitHub Actions before each trading cycle.

Supports multiple data sources with automatic fallback.
"""

import argparse
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import requests
import time
import sys


def download_binance_klines(symbol: str, interval: str = "4h", bars: int = 500):
    """Download klines from Binance with fallback endpoints."""

    symbol_pair = symbol.upper() + "USDT"

    # Try multiple endpoints (some are blocked in certain regions)
    endpoints = [
        "https://data-api.binance.vision/api/v3/klines",  # Data API (less restricted)
        "https://api.binance.com/api/v3/klines",          # Main API
        "https://api1.binance.com/api/v3/klines",         # Mirror 1
        "https://api2.binance.com/api/v3/klines",         # Mirror 2
    ]

    # Calculate timestamps
    end_time = int(datetime.now().timestamp() * 1000)
    interval_hours = {'1h': 1, '4h': 4, '1d': 24}.get(interval, 4)
    days_needed = (bars * interval_hours) / 24 + 1
    start_time = int((datetime.now() - timedelta(days=days_needed)).timestamp() * 1000)

    all_klines = []

    for base_url in endpoints:
        print(f"Trying {base_url.split('/')[2]}...")
        all_klines = []
        current_start = start_time

        try:
            while current_start < end_time and len(all_klines) < bars:
                params = {
                    "symbol": symbol_pair,
                    "interval": interval,
                    "startTime": current_start,
                    "endTime": end_time,
                    "limit": min(1000, bars - len(all_klines))
                }

                response = requests.get(base_url, params=params, timeout=30)

                if response.status_code == 451:
                    print(f"  Blocked (451), trying next endpoint...")
                    break

                response.raise_for_status()
                klines = response.json()

                if not klines:
                    break

                all_klines.extend(klines)
                current_start = klines[-1][0] + 1
                print(f"  Downloaded {len(all_klines)}/{bars} candles", end="\r")
                time.sleep(0.1)

            if len(all_klines) >= bars * 0.9:  # Got at least 90% of requested data
                print(f"\n  Success with {base_url.split('/')[2]}")
                break

        except requests.exceptions.RequestException as e:
            print(f"  Error: {e}")
            continue

    if not all_klines:
        print(f"Failed to download {symbol} data from all endpoints")
        # Try fallback to CryptoCompare
        return download_cryptocompare(symbol, interval, bars)

    # Convert to DataFrame
    df = pd.DataFrame(all_klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    df = df.tail(bars)

    return save_data(df, symbol, interval)


def download_cryptocompare(symbol: str, interval: str = "4h", bars: int = 500):
    """Fallback: Download from CryptoCompare API (free, no restrictions)."""

    print(f"Fallback: Using CryptoCompare for {symbol}...")

    # Map interval to CryptoCompare format
    interval_map = {
        '1h': ('histohour', 1),
        '4h': ('histohour', 4),
        '1d': ('histoday', 1),
    }

    endpoint, aggregate = interval_map.get(interval, ('histohour', 4))
    base_url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"

    params = {
        "fsym": symbol.upper(),
        "tsym": "USDT",
        "limit": min(2000, bars),
        "aggregate": aggregate,
    }

    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get('Response') == 'Error':
            print(f"  CryptoCompare error: {data.get('Message')}")
            return None

        klines = data.get('Data', {}).get('Data', [])

        if not klines:
            print("  No data from CryptoCompare")
            return None

        df = pd.DataFrame(klines)
        df['timestamp'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('timestamp')
        df = df.rename(columns={
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volumefrom': 'volume'
        })
        df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        df = df[df['volume'] > 0]  # Remove empty candles
        df = df.tail(bars)

        print(f"  Got {len(df)} candles from CryptoCompare")
        return save_data(df, symbol, interval)

    except Exception as e:
        print(f"  CryptoCompare error: {e}")
        return None


def save_data(df: pd.DataFrame, symbol: str, interval: str):
    """Save DataFrame to CSV."""

    if df is None or len(df) == 0:
        return None

    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = output_dir / f"{symbol.upper()}_{interval}.csv"
    df.to_csv(filename)

    print(f"Saved: {filename}")
    print(f"  Period: {df.index[0]} to {df.index[-1]}")
    print(f"  Candles: {len(df)}")

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC", help="Symbol (BTC, ETH)")
    parser.add_argument("--timeframe", default="4h", help="Timeframe")
    parser.add_argument("--bars", type=int, default=500, help="Number of candles")

    args = parser.parse_args()

    result = download_binance_klines(args.symbol, args.timeframe, args.bars)

    if result is None:
        print(f"WARNING: Could not download data for {args.symbol}")
        sys.exit(1)


if __name__ == "__main__":
    main()
