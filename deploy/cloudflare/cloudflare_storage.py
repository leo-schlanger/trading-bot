"""
Cloudflare Storage Integration
Usa KV, D1 e R2 como "memória" gratuita do bot.
"""

import os
import json
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class CloudflareConfig:
    """Configuração do Cloudflare."""
    account_id: str = ""
    api_token: str = ""
    kv_namespace_id: str = ""  # Para estado do bot
    d1_database_id: str = ""   # Para trades
    r2_bucket_name: str = ""   # Para modelos/dados

    @classmethod
    def from_env(cls):
        return cls(
            account_id=os.getenv("CF_ACCOUNT_ID", ""),
            api_token=os.getenv("CF_API_TOKEN", ""),
            kv_namespace_id=os.getenv("CF_KV_NAMESPACE_ID", ""),
            d1_database_id=os.getenv("CF_D1_DATABASE_ID", ""),
            r2_bucket_name=os.getenv("CF_R2_BUCKET", "trading-bot"),
        )


class CloudflareKV:
    """
    Cloudflare KV - Key-Value storage para estado do bot.

    Free tier: 100k reads/day, 1k writes/day
    """

    def __init__(self, config: CloudflareConfig):
        self.config = config
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{config.account_id}/storage/kv/namespaces/{config.kv_namespace_id}"
        self.headers = {
            "Authorization": f"Bearer {config.api_token}",
            "Content-Type": "application/json"
        }

    def get(self, key: str) -> Optional[Dict]:
        """Buscar valor do KV."""
        try:
            url = f"{self.base_url}/values/{key}"
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"KV get error: {e}")
            return None

    def put(self, key: str, value: Dict, expiration_ttl: int = None) -> bool:
        """Salvar valor no KV."""
        try:
            url = f"{self.base_url}/values/{key}"
            params = {}
            if expiration_ttl:
                params["expiration_ttl"] = expiration_ttl

            response = requests.put(
                url,
                headers=self.headers,
                params=params,
                data=json.dumps(value)
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"KV put error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Deletar valor do KV."""
        try:
            url = f"{self.base_url}/values/{key}"
            response = requests.delete(url, headers=self.headers)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"KV delete error: {e}")
            return False


class CloudflareD1:
    """
    Cloudflare D1 - SQLite database para histórico de trades.

    Free tier: 5GB storage, 5M rows read/day
    """

    def __init__(self, config: CloudflareConfig):
        self.config = config
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{config.account_id}/d1/database/{config.d1_database_id}"
        self.headers = {
            "Authorization": f"Bearer {config.api_token}",
            "Content-Type": "application/json"
        }

    def execute(self, sql: str, params: List = None) -> Optional[Dict]:
        """Executar query SQL."""
        try:
            url = f"{self.base_url}/query"
            payload = {"sql": sql}
            if params:
                payload["params"] = params

            response = requests.post(url, headers=self.headers, json=payload)

            if response.status_code == 200:
                return response.json()
            logger.error(f"D1 error: {response.text}")
            return None
        except Exception as e:
            logger.error(f"D1 execute error: {e}")
            return None

    def init_tables(self):
        """Criar tabelas necessárias."""
        # Tabela de trades
        self.execute("""
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

        # Tabela de estado
        self.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabela de performance
        self.execute("""
            CREATE TABLE IF NOT EXISTS daily_performance (
                date TEXT PRIMARY KEY,
                capital REAL,
                pnl REAL,
                trades_count INTEGER,
                win_rate REAL,
                regime TEXT
            )
        """)

        logger.info("D1 tables initialized")

    def insert_trade(self, trade: Dict) -> bool:
        """Inserir novo trade."""
        sql = """
            INSERT INTO trades (timestamp, symbol, side, entry_price, size, regime, strategy, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
        """
        result = self.execute(sql, [
            trade.get('timestamp', datetime.now().isoformat()),
            trade.get('symbol', 'BTC'),
            trade.get('side', 'BUY'),
            trade.get('entry_price', 0),
            trade.get('size', 0),
            trade.get('regime', 'unknown'),
            trade.get('strategy', 'unknown')
        ])
        return result is not None

    def close_trade(self, trade_id: int, exit_price: float, pnl: float, pnl_pct: float) -> bool:
        """Fechar trade existente."""
        sql = """
            UPDATE trades
            SET exit_price = ?, pnl = ?, pnl_pct = ?, status = 'closed'
            WHERE id = ?
        """
        result = self.execute(sql, [exit_price, pnl, pnl_pct, trade_id])
        return result is not None

    def get_open_trades(self) -> List[Dict]:
        """Buscar trades abertos."""
        result = self.execute("SELECT * FROM trades WHERE status = 'open'")
        if result and 'result' in result:
            return result['result']
        return []

    def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        """Buscar trades recentes."""
        result = self.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
            [limit]
        )
        if result and 'result' in result:
            return result['result']
        return []


class CloudflareR2:
    """
    Cloudflare R2 - Object storage para modelos ML e dados.

    Free tier: 10GB storage, 1M class A ops, 10M class B ops
    """

    def __init__(self, config: CloudflareConfig):
        self.config = config
        # R2 usa S3-compatible API
        self.endpoint = f"https://{config.account_id}.r2.cloudflarestorage.com"
        self.bucket = config.r2_bucket_name

        # Para R2, é melhor usar boto3 com credenciais S3
        self._s3_client = None

    def _get_s3_client(self):
        """Inicializar cliente S3 para R2."""
        if self._s3_client is None:
            try:
                import boto3
                self._s3_client = boto3.client(
                    's3',
                    endpoint_url=self.endpoint,
                    aws_access_key_id=os.getenv('CF_R2_ACCESS_KEY'),
                    aws_secret_access_key=os.getenv('CF_R2_SECRET_KEY'),
                )
            except ImportError:
                logger.warning("boto3 not installed, R2 operations limited")
        return self._s3_client

    def upload_file(self, local_path: str, remote_key: str) -> bool:
        """Upload arquivo para R2."""
        client = self._get_s3_client()
        if not client:
            return False

        try:
            client.upload_file(local_path, self.bucket, remote_key)
            logger.info(f"Uploaded {local_path} to R2:{remote_key}")
            return True
        except Exception as e:
            logger.error(f"R2 upload error: {e}")
            return False

    def download_file(self, remote_key: str, local_path: str) -> bool:
        """Download arquivo do R2."""
        client = self._get_s3_client()
        if not client:
            return False

        try:
            client.download_file(self.bucket, remote_key, local_path)
            logger.info(f"Downloaded R2:{remote_key} to {local_path}")
            return True
        except Exception as e:
            logger.error(f"R2 download error: {e}")
            return False

    def upload_model(self, model_path: str, model_name: str) -> bool:
        """Upload modelo ML."""
        return self.upload_file(model_path, f"models/{model_name}")

    def download_model(self, model_name: str, local_path: str) -> bool:
        """Download modelo ML."""
        return self.download_file(f"models/{model_name}", local_path)


class BotMemory:
    """
    Interface unificada para a "memória" do bot.
    Combina KV (estado), D1 (trades) e R2 (modelos).
    """

    def __init__(self, config: CloudflareConfig = None):
        self.config = config or CloudflareConfig.from_env()
        self.kv = CloudflareKV(self.config)
        self.d1 = CloudflareD1(self.config)
        self.r2 = CloudflareR2(self.config)

        # Cache local para reduzir chamadas API
        self._state_cache = {}

    def init(self):
        """Inicializar storage."""
        self.d1.init_tables()
        logger.info("Bot memory initialized")

    # === Estado (KV) ===

    def get_state(self, key: str, default: Any = None) -> Any:
        """Buscar estado."""
        if key in self._state_cache:
            return self._state_cache[key]

        value = self.kv.get(f"state:{key}")
        if value:
            self._state_cache[key] = value
            return value
        return default

    def set_state(self, key: str, value: Any) -> bool:
        """Salvar estado."""
        self._state_cache[key] = value
        return self.kv.put(f"state:{key}", value)

    def get_bot_state(self) -> Dict:
        """Buscar estado completo do bot."""
        return self.get_state("bot", {
            "capital": 500.0,
            "position": None,
            "last_regime": None,
            "consecutive_losses": 0,
            "total_trades": 0,
            "total_pnl": 0.0,
            "last_run": None
        })

    def save_bot_state(self, state: Dict) -> bool:
        """Salvar estado do bot."""
        state["last_updated"] = datetime.now().isoformat()
        return self.set_state("bot", state)

    # === Trades (D1) ===

    def record_trade(self, trade: Dict) -> bool:
        """Registrar novo trade."""
        return self.d1.insert_trade(trade)

    def get_open_positions(self) -> List[Dict]:
        """Buscar posições abertas."""
        return self.d1.get_open_trades()

    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Buscar histórico de trades."""
        return self.d1.get_recent_trades(limit)

    # === Modelos (R2) ===

    def save_model(self, local_path: str, model_name: str) -> bool:
        """Salvar modelo no R2."""
        return self.r2.upload_model(local_path, model_name)

    def load_model(self, model_name: str, local_path: str) -> bool:
        """Carregar modelo do R2."""
        return self.r2.download_model(model_name, local_path)

    # === Utilitários ===

    def sync_state(self):
        """Sincronizar cache com KV."""
        for key, value in self._state_cache.items():
            self.kv.put(f"state:{key}", value)
        logger.info("State synced to Cloudflare KV")


# === Uso simplificado ===

def get_memory() -> BotMemory:
    """Factory para obter instância de memória."""
    return BotMemory()


if __name__ == "__main__":
    # Teste básico
    logging.basicConfig(level=logging.INFO)

    memory = get_memory()

    # Verificar configuração
    if not memory.config.account_id:
        print("Configure as variáveis de ambiente:")
        print("  CF_ACCOUNT_ID")
        print("  CF_API_TOKEN")
        print("  CF_KV_NAMESPACE_ID")
        print("  CF_D1_DATABASE_ID")
        print("  CF_R2_BUCKET")
    else:
        print("Cloudflare configurado!")
        memory.init()
