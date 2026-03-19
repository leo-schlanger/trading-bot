"""
Storage Abstraction Layer

Allows switching between different storage backends:
- Local (SQLite + files) - for self-hosted deployments
- Cloudflare (KV + D1 + R2) - for serverless deployments
- Memory (for testing only)

Uso:
    from src.storage import get_storage
    storage = get_storage()  # Auto-detecta baseado em config

    # Mesma API independente do backend:
    storage.save_state("bot", {"capital": 500})
    state = storage.load_state("bot")
    storage.save_trade(trade_data)
    trades = storage.get_trades(limit=50)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict
import json


@dataclass
class Trade:
    """Representa um trade."""
    id: Optional[int] = None
    timestamp: str = ""
    symbol: str = ""
    side: str = ""  # BUY or SELL
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    size: float = 0.0
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    regime: str = ""
    strategy: str = ""
    status: str = "open"  # open, closed, cancelled

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Trade":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BotState:
    """Estado completo do bot."""
    capital: float = 500.0
    position: Optional[Dict] = None
    last_regime: Optional[str] = None
    consecutive_losses: int = 0
    total_trades: int = 0
    total_pnl: float = 0.0
    daily_pnl: float = 0.0
    peak_capital: float = 500.0
    last_run: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "BotState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class StorageBackend(ABC):
    """Interface abstrata para storage."""

    @abstractmethod
    def init(self) -> bool:
        """Inicializa o storage (cria tabelas, etc)."""
        pass

    # === Estado ===

    @abstractmethod
    def save_state(self, key: str, value: Dict) -> bool:
        """Salva estado com uma chave."""
        pass

    @abstractmethod
    def load_state(self, key: str, default: Dict = None) -> Optional[Dict]:
        """Carrega estado por chave."""
        pass

    def save_bot_state(self, state: BotState) -> bool:
        """Salva estado do bot."""
        data = state.to_dict()
        data["last_updated"] = datetime.now().isoformat()
        return self.save_state("bot", data)

    def load_bot_state(self) -> BotState:
        """Carrega estado do bot."""
        data = self.load_state("bot")
        if data:
            return BotState.from_dict(data)
        return BotState()

    # === Trades ===

    @abstractmethod
    def save_trade(self, trade: Trade) -> bool:
        """Salva novo trade."""
        pass

    @abstractmethod
    def update_trade(self, trade_id: int, updates: Dict) -> bool:
        """Atualiza trade existente."""
        pass

    @abstractmethod
    def get_trades(self, limit: int = 50, status: str = None) -> List[Trade]:
        """Busca trades."""
        pass

    @abstractmethod
    def get_open_trades(self) -> List[Trade]:
        """Busca trades abertos."""
        pass

    def close_trade(self, trade_id: int, exit_price: float, pnl: float, pnl_pct: float) -> bool:
        """Fecha um trade."""
        return self.update_trade(trade_id, {
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "status": "closed"
        })

    # === Modelos ML ===

    @abstractmethod
    def save_model(self, name: str, local_path: str) -> bool:
        """Salva modelo ML."""
        pass

    @abstractmethod
    def load_model(self, name: str, local_path: str) -> bool:
        """Carrega modelo ML para arquivo local."""
        pass

    # === Performance ===

    @abstractmethod
    def save_daily_performance(self, date: str, data: Dict) -> bool:
        """Salva performance diária."""
        pass

    @abstractmethod
    def get_performance_history(self, days: int = 30) -> List[Dict]:
        """Busca histórico de performance."""
        pass

    # === Utilitários ===

    def is_configured(self) -> bool:
        """Verifica se o backend está configurado."""
        return True

    def get_backend_name(self) -> str:
        """Retorna nome do backend."""
        return self.__class__.__name__
