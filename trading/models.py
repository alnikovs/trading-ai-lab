from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"  # отсутствие позиции / закрытие


@dataclass
class MarketState:
    """
    Снимок состояния рынка для одного символа в конкретный момент времени.
    Эту структуру используют стратегии и трейдер-агент.
    """
    symbol: str
    timestamp: datetime
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume_24h: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionState:
    """
    Текущее состояние позиции по символу.
    """
    symbol: str
    side: Side
    size: float  # абсолютный размер позиции (в контракте / монете)
    entry_price: float
    unrealized_pnl: float = 0.0
    leverage: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeSignal:
    """
    Сигнал стратегии: что сделать с позицией.
    TraderAgentL1 будет собирать несколько таких сигналов,
    прогонять через risk engine и превращать в реальные ордера.
    """
    symbol: str
    side: Side
    size: float  # желаемый размер (или дельта размера) позиции
    confidence: float  # 0.0–1.0: уверенность стратегии в сигнале
    strategy_id: str
    timestamp: datetime
    price_hint: Optional[float] = None  # желаемая цена исполнения (опционально)
    meta: Dict[str, Any] = field(default_factory=dict)

