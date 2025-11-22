from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Deque, Optional

from trading.models import MarketState, PositionState, Side, TradeSignal
from trading.strategies.base import Strategy


class SimpleMovingAverageStrategy(Strategy):
    """
    Простейшая стратегия на пересечении скользящих средних.
    Это пример для TraderAgentL1: как стратегия превращает данные в сигнал.
    """

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        short_window: int = 10,
        long_window: int = 30,
        min_confidence: float = 0.6,
    ) -> None:
        """
        Инициализировать стратегию скользящих средних.

        :param strategy_id: идентификатор стратегии (для логов и сигналов)
        :param symbol: торговый инструмент
        :param short_window: размер короткого окна SMA
        :param long_window: размер длинного окна SMA
        :param min_confidence: минимальная "уверенность" для генерации сигнала
        """
        super().__init__(strategy_id=strategy_id, symbol=symbol)
        if short_window <= 0 or long_window <= 0:
            raise ValueError("windows must be > 0")
        if short_window >= long_window:
            raise ValueError("short_window must be < long_window")

        self.short_window = short_window
        self.long_window = long_window
        self.min_confidence = min_confidence

        self._short_prices: Deque[float] = deque(maxlen=short_window)
        self._long_prices: Deque[float] = deque(maxlen=long_window)

    def _ma(self, values: Deque[float]) -> Optional[float]:
        if not values:
            return None
        return sum(values) / len(values)

    def generate_signal(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Построить торговый сигнал на основании пересечения краткой и длинной SMA.

        :param market_state: актуальное состояние рынка
        :param position: состояние позиции по символу (не используется на данном уровне)
        :return: TradeSignal или None, если условий для сделки нет
        """
        price = market_state.price
        self._short_prices.append(price)
        self._long_prices.append(price)

        short_ma = self._ma(self._short_prices)
        long_ma = self._ma(self._long_prices)

        # пока не набрали достаточно данных
        if short_ma is None or long_ma is None:
            return None

        # простой сигнал: пересечение MA
        # buy, если короткая MA выше длинной, sell — если ниже
        if short_ma > long_ma:
            side = Side.BUY
        elif short_ma < long_ma:
            side = Side.SELL
        else:
            return None

        # очень простая оценка "уверенности"
        distance = abs(short_ma - long_ma) / price
        confidence = min(1.0, distance * 100)  # примитивно, но для примера достаточно
        if confidence < self.min_confidence:
            return None

        # размер позиции сейчас жёстко задаём, позже это возьмёт на себя risk engine
        size = 1.0

        timestamp = (
            market_state.timestamp
            if isinstance(market_state.timestamp, datetime)
            else datetime.utcnow()
        )

        return TradeSignal(
            symbol=self.symbol,
            side=side,
            size=size,
            confidence=confidence,
            strategy_id=self.strategy_id,
            timestamp=timestamp,
            price_hint=price,
            meta={
                "short_ma": short_ma,
                "long_ma": long_ma,
            },
        )

    def on_market_state(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Поддержка старого интерфейса Strategy; перенаправляет в generate_signal.
        """
        return self.generate_signal(market_state=market_state, position=position)
