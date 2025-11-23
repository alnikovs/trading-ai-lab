"""
Simple moving average crossover strategy used for simulations/backtests.

The strategy compares the latest price with its N-period SMA and emits a signal
only when the price crosses the average. The logic is intentionally deterministic
so it can be unit-tested in isolation.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Deque, Optional

from trading.models import MarketState, PositionState, Side, TradeSignal
from trading.strategies.base import Strategy


class SimpleMAStrategy(Strategy):
    """
    Single-window simple moving average (SMA) crossing strategy.

    The strategy keeps a rolling list of close prices and watches for the latest
    price crossing above or below its SMA. Crossing above triggers a BUY signal
    when we are flat/short, crossing below triggers a SELL signal when we are
    flat/long.
    """

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        window: int = 20,
        min_confidence: float = 0.1,
        trade_size: float = 1.0,
    ) -> None:
        super().__init__(strategy_id=strategy_id, symbol=symbol)
        if window <= 1:
            raise ValueError("window must be greater than 1")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if trade_size <= 0:
            raise ValueError("trade_size must be positive")

        self.window = window
        self.min_confidence = min_confidence
        self.trade_size = trade_size

        self._prices: Deque[float] = deque(maxlen=window)
        self._last_relation: Optional[int] = None  # -1 below, 0 equal, 1 above

    def _compute_sma(self) -> Optional[float]:
        if len(self._prices) < self.window:
            return None
        return sum(self._prices) / self.window

    def _relation_sign(self, price: float, sma: float) -> int:
        if price > sma:
            return 1
        if price < sma:
            return -1
        return 0

    def generate_signal(
        self,
        market_state: MarketState,
        position_state: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Inspect the latest price vs SMA and decide whether to emit a signal.

        Returns None when no trade is needed (i.e. stay flat).
        """

        price = market_state.price
        self._prices.append(price)

        sma = self._compute_sma()
        if sma is None:
            self._last_relation = None
            return None

        relation_sign = self._relation_sign(price, sma)
        position_side = position_state.side if position_state else Side.FLAT

        signal_side: Optional[Side] = None
        if (
            self._last_relation is not None
            and relation_sign > 0
            and self._last_relation <= 0
            and position_side in {Side.FLAT, Side.SELL}
        ):
            signal_side = Side.BUY
        elif (
            self._last_relation is not None
            and relation_sign < 0
            and self._last_relation >= 0
            and position_side in {Side.FLAT, Side.BUY}
        ):
            signal_side = Side.SELL

        self._last_relation = relation_sign
        if signal_side is None:
            return None

        distance_ratio = abs(price - sma) / price if price else 0.0
        confidence = min(1.0, distance_ratio)
        if confidence < self.min_confidence:
            return None

        timestamp = (
            market_state.timestamp
            if isinstance(market_state.timestamp, datetime)
            else datetime.utcnow()
        )

        return TradeSignal(
            symbol=self.symbol,
            side=signal_side,
            size=self.trade_size,
            confidence=confidence,
            strategy_id=self.strategy_id,
            timestamp=timestamp,
            price_hint=price,
            meta={
                "sma": sma,
                "window": self.window,
                "relation_sign": relation_sign,
            },
        )

    def on_market_state(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Adapter hook used by TraderAgentL1.
        """

        return self.generate_signal(market_state=market_state, position_state=position)


class SimpleMovingAverageStrategy(SimpleMAStrategy):
    """
    Backwards-compatible alias for legacy imports.
    """

    pass
