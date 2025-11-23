"""Simple moving average (SMA) crossover strategy.

This module provides a lightweight, deterministic strategy that issues trade
signals when the latest price crosses its N-period simple moving average. It is
designed for research/backtesting use only and does not interact with live
markets directly.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

from trading.models import MarketState, PositionState, Side, TradeSignal
from trading.strategies.base import Strategy


@dataclass
class SimpleMAConfig:
    """Configuration for the simple MA strategy."""

    window: int = 20
    trade_size: float = 1.0
    min_confidence: float = 0.05

    def __post_init__(self) -> None:
        if self.window < 2:
            raise ValueError("SMA window must be >= 2.")
        if self.trade_size <= 0:
            raise ValueError("trade_size must be positive.")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1.")


@dataclass
class SMAWindow:
    """Rolling window helper that computes an N-period simple moving average."""

    length: int
    _values: Deque[float] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.length < 2:
            raise ValueError("SMA window must be >= 2.")
        self._values = deque(maxlen=self.length)

    def push(self, value: float) -> Optional[float]:
        """Add a new value and return the latest SMA when enough data exists."""

        self._values.append(value)
        return self.current

    @property
    def is_ready(self) -> bool:
        """Return True once the window is fully populated."""

        return len(self._values) == self.length

    @property
    def current(self) -> Optional[float]:
        """Return the current SMA value or None if not enough data."""

        if not self.is_ready:
            return None
        return sum(self._values) / self.length

    def clear(self) -> None:
        """Remove all stored prices."""

        self._values.clear()


class SimpleMAStrategy(Strategy):
    """Generates trade signals based on price/SMA crossovers."""

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        *,
        window: int = 20,
        trade_size: float = 1.0,
        min_confidence: float = 0.05,
    ) -> None:
        super().__init__(strategy_id=strategy_id, symbol=symbol)
        self.config = SimpleMAConfig(
            window=window,
            trade_size=trade_size,
            min_confidence=min_confidence,
        )
        self._sma_window = SMAWindow(length=self.config.window)
        self._previous_diff: Optional[float] = None

    def _can_buy(self, position_state: Optional[PositionState]) -> bool:
        if position_state is None:
            return True
        return position_state.side in {Side.FLAT, Side.SELL}

    def _can_sell(self, position_state: Optional[PositionState]) -> bool:
        if position_state is None:
            return True
        return position_state.side in {Side.FLAT, Side.BUY}

    def generate_signal(
        self,
        market_state: MarketState,
        position_state: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """Produce a TradeSignal when the price crosses the configured SMA."""

        price = market_state.price
        sma = self._sma_window.push(price)
        if sma is None:
            # Not enough data collected yet.
            self._previous_diff = None
            return None

        diff = price - sma
        prev_diff = self._previous_diff

        cross_above = bool(prev_diff is not None and prev_diff <= 0 and diff > 0)
        cross_below = bool(prev_diff is not None and prev_diff >= 0 and diff < 0)
        self._previous_diff = diff

        side: Optional[Side] = None
        if cross_above and self._can_buy(position_state):
            side = Side.BUY
        elif cross_below and self._can_sell(position_state):
            side = Side.SELL

        if side is None:
            return None

        confidence = min(1.0, abs(diff) / sma)
        if confidence < self.config.min_confidence:
            return None

        return TradeSignal(
            symbol=self.symbol,
            side=side,
            size=self.config.trade_size,
            confidence=confidence,
            strategy_id=self.strategy_id,
            timestamp=market_state.timestamp,
            price_hint=price,
            meta={"sma": sma, "price": price, "diff": diff},
        )

    def on_market_state(
        self,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """Adapter to the base Strategy interface."""

        return self.generate_signal(market_state=market_state, position_state=position)

    def reset(self) -> None:
        """Clear cached SMA values so the strategy can be reused in a new run."""

        self._sma_window.clear()
        self._previous_diff = None
