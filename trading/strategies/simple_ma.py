"""Research-only simple moving average crossover strategy for backtests."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional

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


class SimpleMAStrategy(Strategy):
    """Generates trade signals when the latest price crosses its SMA."""

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        *,
        window: int = 20,
        trade_size: float = 1.0,
        min_confidence: float = 0.05,
        initial_prices: Optional[Iterable[float]] = None,
    ) -> None:
        super().__init__(strategy_id=strategy_id, symbol=symbol)
        self.config = SimpleMAConfig(
            window=window,
            trade_size=trade_size,
            min_confidence=min_confidence,
        )
        self._prices: Deque[float] = deque(maxlen=self.config.window)
        self._previous_diff: Optional[float] = None
        if initial_prices:
            self.seed_prices(initial_prices)

    def _compute_sma(self) -> Optional[float]:
        if len(self._prices) < self.config.window:
            return None
        return sum(self._prices) / len(self._prices)

    def _can_buy(self, position_state: Optional[PositionState]) -> bool:
        if position_state is None:
            return True
        return position_state.side in {Side.FLAT, Side.SELL}

    def _can_sell(self, position_state: Optional[PositionState]) -> bool:
        if position_state is None:
            return True
        return position_state.side in {Side.FLAT, Side.BUY}

    def seed_prices(self, prices: Iterable[float]) -> None:
        """
        Preload price history to warm up the SMA window, useful in tests.
        """

        for price in prices:
            self._prices.append(float(price))

        last_price = self._prices[-1] if self._prices else None
        sma = self._compute_sma()
        self._previous_diff = (
            None if last_price is None or sma is None else last_price - sma
        )

    @property
    def is_warmed_up(self) -> bool:
        """Return True when enough prices were observed to compute the SMA."""

        return len(self._prices) >= self.config.window

    def _calculate_confidence(self, diff: float, sma: float) -> float:
        """
        Convert the diff value to a 0..1 confidence score with safe zero handling.
        """

        if sma == 0:
            return 1.0 if diff != 0 else 0.0
        return min(1.0, abs(diff) / abs(sma))

    def generate_signal(
        self,
        market_state: MarketState,
        position_state: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Produce a trade signal when the latest price crosses the configured SMA.

        The signal is emitted only when:
        - the SMA window is warmed up,
        - a crossover happens,
        - the current position permits acting on that crossover,
        - the computed confidence exceeds the configured threshold.
        """

        price = market_state.price
        self._prices.append(price)

        sma = self._compute_sma()
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

        confidence = self._calculate_confidence(diff, sma)
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
