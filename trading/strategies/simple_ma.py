"""Simple moving average (SMA) crossover strategy."""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional

from trading.models import MarketState, PositionState, Side, TradeSignal
from trading.strategies.base import Strategy


class SimpleMAStrategy(Strategy):
    """
    Deterministic SMA crossover strategy.

    The strategy monitors the last ``window`` close prices and reacts when the
    price crosses its SMA:
    * price crosses above SMA while flat/short -> BUY
    * price crosses below SMA while flat/long -> SELL
    * otherwise -> no signal (aka stay flat)
    """

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        window: int = 20,
        order_size: float = 1.0,
        min_confidence: float = 0.0,
    ) -> None:
        super().__init__(strategy_id=strategy_id, symbol=symbol)
        if window < 2:
            raise ValueError("window must be >= 2 to evaluate SMA crossings")
        if order_size <= 0:
            raise ValueError("order_size must be positive")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")

        self.window = window
        self.order_size = order_size
        self.min_confidence = min_confidence

        self._prices: Deque[float] = deque(maxlen=window)
        self._previous_price: Optional[float] = None
        self._previous_sma: Optional[float] = None

    def _compute_sma(self) -> Optional[float]:
        if len(self._prices) < self.window:
            return None
        return sum(self._prices) / self.window

    @staticmethod
    def _calculate_confidence(price: float, sma: float) -> float:
        if sma == 0:
            return 0.0
        return min(1.0, abs(price - sma) / abs(sma))

    def generate_signal(
        self,
        market_state: MarketState,
        position_state: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Generate a TradeSignal based on the latest market snapshot.

        Returns None when no crossing is detected (meaning the strategy stays flat).
        """

        price = market_state.price
        self._prices.append(price)

        sma = self._compute_sma()
        prev_price = self._previous_price
        prev_sma = self._previous_sma

        self._previous_price = price
        self._previous_sma = sma

        # Not enough data yet to form a window
        if sma is None or prev_price is None or prev_sma is None:
            return None

        crossed_above = prev_price <= prev_sma and price > sma
        crossed_below = prev_price >= prev_sma and price < sma

        if crossed_above and self._can_open_long(position_state):
            side = Side.BUY
        elif crossed_below and self._can_open_short(position_state):
            side = Side.SELL
        else:
            return None

        confidence = self._calculate_confidence(price, sma)
        if confidence < self.min_confidence:
            return None

        return TradeSignal(
            symbol=self.symbol,
            side=side,
            size=self.order_size,
            confidence=confidence,
            strategy_id=self.strategy_id,
            timestamp=market_state.timestamp,
            price_hint=price,
            meta={
                "sma": sma,
                "window": self.window,
            },
        )

    def _can_open_long(self, position_state: Optional[PositionState]) -> bool:
        if position_state is None:
            return True
        return position_state.side in (Side.FLAT, Side.SELL)

    def _can_open_short(self, position_state: Optional[PositionState]) -> bool:
        if position_state is None:
            return True
        return position_state.side in (Side.FLAT, Side.BUY)

    def on_market_state(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Backwards-compatible entrypoint used by TraderAgentL1.
        """

        return self.generate_signal(market_state, position)


# Backwards-compatible alias used by older modules/tests.
SimpleMovingAverageStrategy = SimpleMAStrategy
