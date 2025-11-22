from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from trading.models import MarketState, PositionState, TradeSignal
from trading.strategies.base import Strategy


@dataclass(frozen=True)
class SimpleMAConfig:
    """
    Параметры стратегии простых скользящих средних.

    Логика сигналов появится на следующих шагах; сейчас важно зафиксировать
    контракт конфигурации и базовую валидацию.
    """

    short_window: int = 10
    long_window: int = 30
    min_confidence: float = 0.6

    def __post_init__(self) -> None:
        if self.short_window <= 0 or self.long_window <= 0:
            raise ValueError("MA windows must be positive integers.")
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be smaller than long_window.")
        if not 0.0 < self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be within (0, 1].")


class SimpleMAStrategy(Strategy):
    """
    Каркас стратегии простого пересечения MA.

    Данный класс содержит только структуру и заглушки без бизнес-логики.
    """

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        config: Optional[SimpleMAConfig] = None,
    ) -> None:
        super().__init__(strategy_id=strategy_id, symbol=symbol)
        self.config = config or SimpleMAConfig()
        self._short_prices: Deque[float] = deque(maxlen=self.config.short_window)
        self._long_prices: Deque[float] = deque(maxlen=self.config.long_window)

    def reset(self) -> None:
        """Сброс накопленного состояния (например, при рестарте агента)."""
        self._short_prices.clear()
        self._long_prices.clear()

    def _update_state(self, market_state: MarketState) -> None:
        """
        Обновляет внутреннее состояние стратегии свежими данными рынка.
        Реальная реализация появится на следующем шаге.
        """
        del market_state  # заглушка, чтобы избежать предупреждений линтера

    def _build_signal(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Конвертирует состояние в сигнал. Пока возвращает None, так как логика
        будет добавлена на следующих шагах.
        """
        del market_state, position
        return None

    def on_market_state(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Основная точка входа стратегии.

        Последовательность шагов:
        1. Обновить внутреннее состояние (буферы цен, вспомогательные метрики).
        2. Построить торговый сигнал.
        """
        self._update_state(market_state)
        return self._build_signal(market_state, position)
