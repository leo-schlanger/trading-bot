"""
Local Storage Backend

Uses SQLite for data and filesystem for models.
Ideal for self-hosted deployments.

Advantages:
- Zero external dependencies
- Works offline
- Local data storage
- Simple backup (copy data/ folder)
"""

import os
import json
import sqlite3
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import StorageBackend, Trade, BotState

logger = logging.getLogger(__name__)


class LocalStorage(StorageBackend):
    """
    Storage local usando SQLite + arquivos.

    Estrutura:
        data/
        ├── bot.db          # SQLite database
        ├── state/          # JSON state files
        └── models/         # ML models (.pkl)
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "bot.db"
        self.state_dir = self.data_dir / "state"
        self.models_dir = self.data_dir / "models"

        # Criar diretórios
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(exist_ok=True)
        self.models_dir.mkdir(exist_ok=True)

        self._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        """Obtém conexão SQLite."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init(self) -> bool:
        """Cria tabelas necessárias."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            # Tabela de trades
            cursor.execute("""
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

            # Tabela de performance diária
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_performance (
                    date TEXT PRIMARY KEY,
                    capital REAL,
                    pnl REAL,
                    trades_count INTEGER,
                    win_rate REAL,
                    regime TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Índices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")

            conn.commit()
            logger.info(f"Local storage initialized at {self.data_dir}")
            return True

        except Exception as e:
            logger.error(f"Error initializing local storage: {e}")
            return False

    # === Estado ===

    def save_state(self, key: str, value: Dict) -> bool:
        """Salva estado em arquivo JSON."""
        try:
            state_file = self.state_dir / f"{key}.json"
            with open(state_file, "w") as f:
                json.dump(value, f, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"Error saving state '{key}': {e}")
            return False

    def load_state(self, key: str, default: Dict = None) -> Optional[Dict]:
        """Carrega estado de arquivo JSON."""
        try:
            state_file = self.state_dir / f"{key}.json"
            if state_file.exists():
                with open(state_file, "r") as f:
                    return json.load(f)
            return default
        except Exception as e:
            logger.error(f"Error loading state '{key}': {e}")
            return default

    # === Trades ===

    def save_trade(self, trade: Trade) -> bool:
        """Insere novo trade no SQLite."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO trades (timestamp, symbol, side, entry_price, size, regime, strategy, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.timestamp or datetime.now().isoformat(),
                trade.symbol,
                trade.side,
                trade.entry_price,
                trade.size,
                trade.regime,
                trade.strategy,
                trade.status
            ))

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"Error saving trade: {e}")
            return False

    def update_trade(self, trade_id: int, updates: Dict) -> bool:
        """Atualiza trade existente."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [trade_id]

            cursor.execute(f"UPDATE trades SET {set_clause} WHERE id = ?", values)
            conn.commit()
            return True

        except Exception as e:
            logger.error(f"Error updating trade {trade_id}: {e}")
            return False

    def get_trades(self, limit: int = 50, status: str = None) -> List[Trade]:
        """Busca trades do SQLite."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            if status:
                cursor.execute(
                    "SELECT * FROM trades WHERE status = ? ORDER BY timestamp DESC LIMIT ?",
                    (status, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )

            rows = cursor.fetchall()
            return [Trade.from_dict(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting trades: {e}")
            return []

    def get_open_trades(self) -> List[Trade]:
        """Busca trades abertos."""
        return self.get_trades(limit=100, status="open")

    # === Modelos ML ===

    def save_model(self, name: str, local_path: str) -> bool:
        """Copia modelo para pasta de modelos."""
        try:
            src = Path(local_path)
            dst = self.models_dir / name

            if src.exists():
                shutil.copy2(src, dst)
                logger.info(f"Model saved: {name}")
                return True
            else:
                logger.error(f"Source model not found: {local_path}")
                return False

        except Exception as e:
            logger.error(f"Error saving model '{name}': {e}")
            return False

    def load_model(self, name: str, local_path: str) -> bool:
        """Copia modelo da pasta de modelos."""
        try:
            src = self.models_dir / name
            dst = Path(local_path)

            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                logger.info(f"Model loaded: {name}")
                return True
            else:
                logger.warning(f"Model not found: {name}")
                return False

        except Exception as e:
            logger.error(f"Error loading model '{name}': {e}")
            return False

    # === Performance ===

    def save_daily_performance(self, date: str, data: Dict) -> bool:
        """Salva performance diária."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO daily_performance (date, capital, pnl, trades_count, win_rate, regime)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                date,
                data.get("capital", 0),
                data.get("pnl", 0),
                data.get("trades_count", 0),
                data.get("win_rate", 0),
                data.get("regime", "")
            ))

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"Error saving daily performance: {e}")
            return False

    def get_performance_history(self, days: int = 30) -> List[Dict]:
        """Busca histórico de performance."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM daily_performance ORDER BY date DESC LIMIT ?",
                (days,)
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Error getting performance history: {e}")
            return []

    def close(self):
        """Fecha conexão com banco."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()
