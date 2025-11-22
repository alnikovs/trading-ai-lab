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
    def generate_signal(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Построить торговый сигнал по текущему состоянию рынка и позиции.

        :param market_state: снимок текущего рынка
        :param position: текущее состояние позиции по символу (если есть)
        :return: TradeSignal или None
        """
        raise NotImplementedError

    def on_market_state(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Обёртка для обратной совместимости, перенаправляющая вызов в generate_signal.
        """
        return self.generate_signal(market_state=market_state, position=position)
