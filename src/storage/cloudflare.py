"""
Cloudflare Storage Backend

Uses KV for state, D1 for trades, R2 for models.
Ideal for serverless/stateless compute environments.

Advantages:
- No server required
- High availability
- Generous free tier
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import StorageBackend, Trade, BotState

logger = logging.getLogger(__name__)


class CloudflareStorage(StorageBackend):
    """
    Storage usando serviços Cloudflare.

    Requer variáveis de ambiente:
    - CF_ACCOUNT_ID
    - CF_API_TOKEN
    - CF_KV_NAMESPACE_ID
    - CF_D1_DATABASE_ID
    - CF_R2_ACCESS_KEY
    - CF_R2_SECRET_KEY
    """

    def __init__(self):
        self.account_id = os.getenv("CF_ACCOUNT_ID", "")
        self.api_token = os.getenv("CF_API_TOKEN", "")
        self.kv_namespace_id = os.getenv("CF_KV_NAMESPACE_ID", "")
        self.d1_database_id = os.getenv("CF_D1_DATABASE_ID", "")
        self.r2_access_key = os.getenv("CF_R2_ACCESS_KEY", "")
        self.r2_secret_key = os.getenv("CF_R2_SECRET_KEY", "")
        self.r2_bucket = os.getenv("CF_R2_BUCKET", "trading-bot")

        self._headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        self._s3_client = None

    def is_configured(self) -> bool:
        """Verifica se Cloudflare está configurado."""
        return bool(self.account_id and self.api_token)

    def _kv_url(self, key: str) -> str:
        """URL para operações KV."""
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.kv_namespace_id}/values/{key}"

    def _d1_url(self) -> str:
        """URL para operações D1."""
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/d1/database/{self.d1_database_id}/query"

    def _get_s3_client(self):
        """Obtém cliente S3 para R2."""
        if self._s3_client is None and self.r2_access_key:
            try:
                import boto3
                self._s3_client = boto3.client(
                    's3',
                    endpoint_url=f'https://{self.account_id}.r2.cloudflarestorage.com',
                    aws_access_key_id=self.r2_access_key,
                    aws_secret_access_key=self.r2_secret_key,
                )
            except ImportError:
                logger.warning("boto3 not installed, R2 unavailable")
        return self._s3_client

    def init(self) -> bool:
        """Inicializa tabelas D1."""
        try:
            import requests

            # Criar tabela de trades
            self._d1_execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    size REAL,
                    pnl REAL,
                    pnl_pct REAL,
                    regime TEXT,
                    strategy TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Criar tabela de performance
            self._d1_execute("""
                CREATE TABLE IF NOT EXISTS daily_performance (
                    date TEXT PRIMARY KEY,
                    capital REAL,
                    pnl REAL,
                    trades_count INTEGER,
                    win_rate REAL,
                    regime TEXT
                )
            """)

            logger.info("Cloudflare D1 tables initialized")
            return True

        except Exception as e:
            logger.error(f"Error initializing Cloudflare storage: {e}")
            return False

    def _d1_execute(self, sql: str, params: List = None) -> Optional[Dict]:
        """Executa query no D1."""
        try:
            import requests

            payload = {"sql": sql}
            if params:
                payload["params"] = params

            response = requests.post(
                self._d1_url(),
                headers=self._headers,
                json=payload
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"D1 error: {response.text}")
                return None

        except Exception as e:
            logger.error(f"D1 execute error: {e}")
            return None

    # === Estado (KV) ===

    def save_state(self, key: str, value: Dict) -> bool:
        """Salva estado no KV."""
        try:
            import requests

            response = requests.put(
                self._kv_url(f"state:{key}"),
                headers=self._headers,
                data=json.dumps(value)
            )
            return response.status_code == 200

        except Exception as e:
            logger.error(f"KV save error: {e}")
            return False

    def load_state(self, key: str, default: Dict = None) -> Optional[Dict]:
        """Carrega estado do KV."""
        try:
            import requests

            response = requests.get(
                self._kv_url(f"state:{key}"),
                headers=self._headers
            )

            if response.status_code == 200:
                return response.json()
            return default

        except Exception as e:
            logger.error(f"KV load error: {e}")
            return default

    # === Trades (D1) ===

    def save_trade(self, trade: Trade) -> bool:
        """Salva trade no D1."""
        result = self._d1_execute(
            """
            INSERT INTO trades (timestamp, symbol, side, entry_price, size, regime, strategy, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                trade.timestamp or datetime.now().isoformat(),
                trade.symbol,
                trade.side,
                trade.entry_price,
                trade.size,
                trade.regime,
                trade.strategy,
                trade.status
            ]
        )
        return result is not None

    def update_trade(self, trade_id: int, updates: Dict) -> bool:
        """Atualiza trade no D1."""
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        params = list(updates.values()) + [trade_id]

        result = self._d1_execute(
            f"UPDATE trades SET {set_clause} WHERE id = ?",
            params
        )
        return result is not None

    def get_trades(self, limit: int = 50, status: str = None) -> List[Trade]:
        """Busca trades do D1."""
        if status:
            result = self._d1_execute(
                "SELECT * FROM trades WHERE status = ? ORDER BY timestamp DESC LIMIT ?",
                [status, limit]
            )
        else:
            result = self._d1_execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
                [limit]
            )

        if result and "result" in result:
            return [Trade.from_dict(row) for row in result["result"]]
        return []

    def get_open_trades(self) -> List[Trade]:
        """Busca trades abertos."""
        return self.get_trades(limit=100, status="open")

    # === Modelos (R2) ===

    def save_model(self, name: str, local_path: str) -> bool:
        """Faz upload do modelo para R2."""
        client = self._get_s3_client()
        if not client:
            return False

        try:
            client.upload_file(local_path, self.r2_bucket, f"models/{name}")
            logger.info(f"Model uploaded to R2: {name}")
            return True
        except Exception as e:
            logger.error(f"R2 upload error: {e}")
            return False

    def load_model(self, name: str, local_path: str) -> bool:
        """Baixa modelo do R2."""
        client = self._get_s3_client()
        if not client:
            return False

        try:
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            client.download_file(self.r2_bucket, f"models/{name}", local_path)
            logger.info(f"Model downloaded from R2: {name}")
            return True
        except Exception as e:
            logger.error(f"R2 download error: {e}")
            return False

    # === Performance ===

    def save_daily_performance(self, date: str, data: Dict) -> bool:
        """Salva performance no D1."""
        result = self._d1_execute(
            """
            INSERT OR REPLACE INTO daily_performance (date, capital, pnl, trades_count, win_rate, regime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                date,
                data.get("capital", 0),
                data.get("pnl", 0),
                data.get("trades_count", 0),
                data.get("win_rate", 0),
                data.get("regime", "")
            ]
        )
        return result is not None

    def get_performance_history(self, days: int = 30) -> List[Dict]:
        """Busca histórico de performance."""
        result = self._d1_execute(
            "SELECT * FROM daily_performance ORDER BY date DESC LIMIT ?",
            [days]
        )

        if result and "result" in result:
            return result["result"]
        return []
