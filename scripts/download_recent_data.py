"""
Download recent market data for Drift Protocol trading.

Data sources (in order of preference):
1. Drift Historical Data API
2. Pyth Network (Drift's oracle)
3. Birdeye (Solana aggregator)
4. CryptoCompare (fallback)
"""

import argparse
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import requests
import time
import sys


def download_drift_data(symbol: str, interval: str = "4h", bars: int = 500):
    """Download historical data from Drift's API."""

    print(f"Trying Drift API for {symbol}...")

    # Drift market indices
    market_map = {
        "BTC": 0,   # BTC-PERP
        "ETH": 1,   # ETH-PERP
        "SOL": 2,   # SOL-PERP
    }

    market_index = market_map.get(symbol.upper())
    if market_index is None:
        print(f"  Market {symbol} not found on Drift")
        return None

    # Drift historical data API
    base_url = "https://mainnet-beta.api.drift.trade/trades"

    # Calculate time range
    interval_hours = {'1h': 1, '4h': 4, '1d': 24}.get(interval, 4)
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=bars * interval_hours)

    try:
        params = {
            "marketIndex": market_index,
            "marketType": "perp",
            "startTime": int(start_time.timestamp()),
            "endTime": int(end_time.timestamp()),
        }

        response = requests.get(base_url, params=params, timeout=30)

        if response.status_code != 200:
            print(f"  Drift API returned {response.status_code}")
            return None

        data = response.json()

        if not data or 'trades' not in data:
            print("  No trade data from Drift")
            return None

        # Aggregate trades into OHLCV candles
        trades_df = pd.DataFrame(data['trades'])
        if trades_df.empty:
            return None

        trades_df['timestamp'] = pd.to_datetime(trades_df['ts'], unit='s')
        trades_df['price'] = trades_df['price'].astype(float) / 1e6  # Drift uses 6 decimals
        trades_df['size'] = trades_df['baseAssetAmount'].astype(float) / 1e9

        # Resample to candles
        df = trades_df.set_index('timestamp').resample(interval).agg({
            'price': ['first', 'max', 'min', 'last'],
            'size': 'sum'
        })
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        df = df.dropna()

        if len(df) > 0:
            print(f"  Got {len(df)} candles from Drift")
            return save_data(df.tail(bars), symbol, interval)

    except Exception as e:
        print(f"  Drift API error: {e}")

    return None


def download_pyth_data(symbol: str, interval: str = "4h", bars: int = 500):
    """Download from Pyth Network (Drift's oracle source)."""

    print(f"Trying Pyth Network for {symbol}...")

    # Pyth price feed IDs
    pyth_feeds = {
        "BTC": "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
        "ETH": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
        "SOL": "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    }

    feed_id = pyth_feeds.get(symbol.upper())
    if not feed_id:
        print(f"  No Pyth feed for {symbol}")
        return None

    # Pyth Benchmarks API (historical data)
    base_url = f"https://benchmarks.pyth.network/v1/shims/tradingview/history"

    interval_map = {'1h': '60', '4h': '240', '1d': 'D'}
    tf = interval_map.get(interval, '240')

    end_time = int(datetime.now().timestamp())
    interval_hours = {'1h': 1, '4h': 4, '1d': 24}.get(interval, 4)
    start_time = int((datetime.now() - timedelta(hours=bars * interval_hours)).timestamp())

    try:
        params = {
            "symbol": f"Crypto.{symbol.upper()}/USD",
            "resolution": tf,
            "from": start_time,
            "to": end_time,
        }

        response = requests.get(base_url, params=params, timeout=30)

        if response.status_code != 200:
            print(f"  Pyth returned {response.status_code}")
            return None

        data = response.json()

        if data.get('s') != 'ok':
            print(f"  Pyth error: {data.get('s')}")
            return None

        df = pd.DataFrame({
            'timestamp': pd.to_datetime(data['t'], unit='s'),
            'open': data['o'],
            'high': data['h'],
            'low': data['l'],
            'close': data['c'],
            'volume': data.get('v', [0] * len(data['t']))
        })

        df = df.set_index('timestamp')
        df = df.astype(float)

        print(f"  Got {len(df)} candles from Pyth")
        return save_data(df.tail(bars), symbol, interval)

    except Exception as e:
        print(f"  Pyth error: {e}")

    return None


def download_birdeye_data(symbol: str, interval: str = "4h", bars: int = 500):
    """Download from Birdeye (Solana data aggregator)."""

    print(f"Trying Birdeye for {symbol}...")

    # Token addresses on Solana
    token_addresses = {
        "BTC": "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # Wrapped BTC
        "ETH": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",  # Wrapped ETH
        "SOL": "So11111111111111111111111111111111111111112",    # Native SOL
    }

    address = token_addresses.get(symbol.upper())
    if not address:
        print(f"  No Birdeye address for {symbol}")
        return None

    base_url = f"https://public-api.birdeye.so/defi/ohlcv"

    interval_map = {'1h': '1H', '4h': '4H', '1d': '1D'}
    tf = interval_map.get(interval, '4H')

    try:
        headers = {"X-API-KEY": "public"}  # Public tier
        params = {
            "address": address,
            "type": tf,
            "time_from": int((datetime.now() - timedelta(days=bars//6)).timestamp()),
            "time_to": int(datetime.now().timestamp()),
        }

        response = requests.get(base_url, headers=headers, params=params, timeout=30)

        if response.status_code != 200:
            print(f"  Birdeye returned {response.status_code}")
            return None

        data = response.json()
        items = data.get('data', {}).get('items', [])

        if not items:
            print("  No data from Birdeye")
            return None

        df = pd.DataFrame(items)
        df['timestamp'] = pd.to_datetime(df['unixTime'], unit='s')
        df = df.set_index('timestamp')
        df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'})
        df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

        print(f"  Got {len(df)} candles from Birdeye")
        return save_data(df.tail(bars), symbol, interval)

    except Exception as e:
        print(f"  Birdeye error: {e}")

    return None


def download_cryptocompare(symbol: str, interval: str = "4h", bars: int = 500):
    """Fallback: CryptoCompare (general crypto data)."""

    print(f"Fallback: Using CryptoCompare for {symbol}...")

    interval_map = {
        '1h': ('histohour', 1),
        '4h': ('histohour', 4),
        '1d': ('histoday', 1),
    }

    endpoint, aggregate = interval_map.get(interval, ('histohour', 4))
    base_url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"

    try:
        params = {
            "fsym": symbol.upper(),
            "tsym": "USD",
            "limit": min(2000, bars),
            "aggregate": aggregate,
        }

        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get('Response') == 'Error':
            print(f"  CryptoCompare error: {data.get('Message')}")
            return None

        klines = data.get('Data', {}).get('Data', [])

        if not klines:
            return None

        df = pd.DataFrame(klines)
        df['timestamp'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('timestamp')
        df = df.rename(columns={'volumefrom': 'volume'})
        df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        df = df[df['volume'] > 0]

        print(f"  Got {len(df)} candles from CryptoCompare")
        return save_data(df.tail(bars), symbol, interval)

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


def download_data(symbol: str, interval: str = "4h", bars: int = 500):
    """Try all data sources in order of preference."""

    # Try sources in order
    sources = [
        download_pyth_data,       # Pyth (Drift's oracle) - most accurate
        download_drift_data,      # Drift direct
        download_birdeye_data,    # Birdeye (Solana aggregator)
        download_cryptocompare,   # Fallback
    ]

    for source in sources:
        result = source(symbol, interval, bars)
        if result is not None and len(result) >= bars * 0.5:
            return result

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC", help="Symbol (BTC, ETH, SOL)")
    parser.add_argument("--timeframe", default="4h", help="Timeframe")
    parser.add_argument("--bars", type=int, default=500, help="Number of candles")

    args = parser.parse_args()

    result = download_data(args.symbol, args.timeframe, args.bars)

    if result is None:
        print(f"ERROR: Could not download data for {args.symbol}")
        sys.exit(1)


if __name__ == "__main__":
    main()
