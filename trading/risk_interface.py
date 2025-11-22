from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List

from trading.models import PositionState, TradeSignal


class RiskEngineInterface(ABC):
    """
    Интерфейс для модуля управления рисками.
    Конкретная реализация будет жить отдельно (например, в orchestrator или trading.risk),
    но TraderAgentL1 будет работать через этот интерфейс.
    """

    @abstractmethod
    def filter_signals(
        self,
        signals: Iterable[TradeSignal],
        positions: Iterable[PositionState],
    ) -> List[TradeSignal]:
        """
        Принимает сырые сигналы стратегий и текущее состояние позиций,
        возвращает только те сигналы, которые проходят риск-фильтры
        (лимиты по плечу, объёму, дневному риску и т.д.).
        """
        raise NotImplementedError
