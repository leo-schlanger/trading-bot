"""
Script para baixar dados históricos.
Fontes gratuitas: CryptoDataDownload, Binance, etc.
"""

import os
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
import zipfile
import io


# Diretório de dados
DATA_DIR = Path(__file__).parent.parent / "data" / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_cryptodatadownload(symbol: str = "SOLUSDT",
                                 exchange: str = "Binance",
                                 timeframe: str = "1h") -> pd.DataFrame:
    """
    Baixa dados do CryptoDataDownload.
    Dados gratuitos de alta qualidade.
    """
    # Mapear timeframes
    tf_map = {
        "1m": "minute",
        "1h": "hour",
        "1d": "day"
    }
    tf = tf_map.get(timeframe, "hour")

    # URL do CryptoDataDownload
    url = f"https://www.cryptodatadownload.com/cdd/{exchange}_{symbol}_{tf}.csv"

    print(f"Baixando dados de {url}...")

    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        # Pular primeira linha (disclaimer)
        lines = response.text.split('\n')
        csv_content = '\n'.join(lines[1:])

        df = pd.read_csv(io.StringIO(csv_content))

        # Padronizar colunas
        df.columns = df.columns.str.lower().str.strip()

        # Renomear colunas comuns
        col_map = {
            'unix': 'timestamp',
            'date': 'datetime',
            'symbol': 'symbol',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume',
            'volume usdt': 'volume_quote',
            'tradecount': 'trades'
        }

        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Converter timestamp
        if 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        elif 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])

        df = df.set_index('datetime')
        df = df.sort_index()

        # Manter apenas OHLCV
        cols = ['open', 'high', 'low', 'close', 'volume']
        df = df[[c for c in cols if c in df.columns]]

        print(f"Baixado: {len(df)} registros de {df.index.min()} a {df.index.max()}")

        return df

    except Exception as e:
        print(f"Erro ao baixar do CryptoDataDownload: {e}")
        return pd.DataFrame()


def download_binance_klines(symbol: str = "SOLUSDT",
                            interval: str = "1h",
                            start_date: str = "2022-01-01",
                            end_date: str = None) -> pd.DataFrame:
    """
    Baixa dados da API pública da Binance.
    Limite de 1000 candles por request.
    """
    base_url = "https://api.binance.com/api/v3/klines"

    start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
    end_ts = int(pd.Timestamp(end_date or datetime.now()).timestamp() * 1000)

    all_data = []
    current_start = start_ts

    print(f"Baixando {symbol} {interval} da Binance...")

    while current_start < end_ts:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "limit": 1000
        }

        try:
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            all_data.extend(data)

            # Próximo batch
            current_start = data[-1][0] + 1

            print(f"  Baixados {len(all_data)} candles...")

        except Exception as e:
            print(f"Erro: {e}")
            break

    if not all_data:
        return pd.DataFrame()

    # Converter para DataFrame
    df = pd.DataFrame(all_data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('datetime')

    # Converter tipos
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    df = df[['open', 'high', 'low', 'close', 'volume']]
    df = df.sort_index()

    print(f"Total: {len(df)} candles de {df.index.min()} a {df.index.max()}")

    return df


def save_data(df: pd.DataFrame, filename: str):
    """Salva dados em CSV."""
    filepath = DATA_DIR / filename
    df.to_csv(filepath)
    print(f"Salvo em: {filepath}")


def load_data(filename: str) -> pd.DataFrame:
    """Carrega dados de CSV."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        return df
    return pd.DataFrame()


def download_all_timeframes(symbol: str = "SOLUSDT"):
    """Baixa dados em múltiplos timeframes."""
    timeframes = ["1h", "4h", "1d"]

    for tf in timeframes:
        print(f"\n{'='*50}")
        print(f"Baixando {symbol} {tf}")
        print('='*50)

        # Tentar Binance primeiro
        df = download_binance_klines(
            symbol=symbol,
            interval=tf,
            start_date="2022-01-01"
        )

        if df.empty:
            print("Binance falhou, tentando CryptoDataDownload...")
            df = download_cryptodatadownload(
                symbol=symbol,
                timeframe=tf
            )

        if not df.empty:
            filename = f"{symbol}_{tf}.csv"
            save_data(df, filename)
        else:
            print(f"Não foi possível baixar dados para {symbol} {tf}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download de dados históricos")
    parser.add_argument("--symbol", default="SOLUSDT", help="Par de trading")
    parser.add_argument("--timeframe", default="1h", help="Timeframe (1m, 1h, 4h, 1d)")
    parser.add_argument("--start", default="2022-01-01", help="Data inicial")
    parser.add_argument("--all", action="store_true", help="Baixar todos os timeframes")

    args = parser.parse_args()

    if args.all:
        download_all_timeframes(args.symbol)
    else:
        df = download_binance_klines(
            symbol=args.symbol,
            interval=args.timeframe,
            start_date=args.start
        )

        if not df.empty:
            filename = f"{args.symbol}_{args.timeframe}.csv"
            save_data(df, filename)
