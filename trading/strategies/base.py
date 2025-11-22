from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from trading.models import MarketState, PositionState, TradeSignal


class Strategy(ABC):
    """
    Базовый класс стратегии.
    Стратегия получает MarketState + текущее состояние позиции
    и возвращает TradeSignal (или None, если действий нет).
    """

    def __init__(self, strategy_id: str, symbol: str) -> None:
        self.strategy_id = strategy_id
        self.symbol = symbol

    @abstractmethod
    def on_market_state(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Основной метод стратегии.

        :param market_state: снимок текущего рынка
        :param position: текущее состояние позиции по символу (если есть)
        :return: TradeSignal или None
        """
        raise NotImplementedError
