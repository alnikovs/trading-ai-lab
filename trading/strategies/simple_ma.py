from __future__ import annotations

from collections import deque
from typing import Deque, Optional

from trading.models import MarketState, PositionState, TradeSignal
from trading.strategies.base import Strategy


class SimpleMAStrategy(Strategy):
    """
    Каркас стратегии пересечения скользящих средних.
    Реальная логика сигналов будет добавлена на следующих шагах DevFlow.
    """

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        short_window: int = 10,
        long_window: int = 30,
        min_confidence: float = 0.6,
    ) -> None:
        super().__init__(strategy_id=strategy_id, symbol=symbol)
        self._validate_windows(short_window, long_window)

        self.short_window = short_window
        self.long_window = long_window
        self.min_confidence = min_confidence

        self._short_prices: Deque[float] = deque(maxlen=short_window)
        self._long_prices: Deque[float] = deque(maxlen=long_window)

    @staticmethod
    def _validate_windows(short_window: int, long_window: int) -> None:
        if short_window <= 0 or long_window <= 0:
            raise ValueError("windows must be > 0")
        if short_window >= long_window:
            raise ValueError("short_window must be < long_window")

    def reset(self) -> None:
        """Очистить накопленные данные перед перезапуском стратегии."""
        self._short_prices.clear()
        self._long_prices.clear()

    def on_market_state(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Обновляет внутреннее состояние рынка и возвращает заглушку сигнала.
        """
        self._ingest_price(market_state.price)
        return self._build_signal_stub(market_state, position)

    def _ingest_price(self, price: float) -> None:
        """Сохраняет цену в буферах скользящих окон."""
        self._short_prices.append(price)
        self._long_prices.append(price)

    def _build_signal_stub(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Заглушка формирования сигнала.
        Здесь появится логика пересечения средних на следующих шагах.
        """
        _ = (market_state, position)  # явно указываем, что аргументы пока не используются
        return None
