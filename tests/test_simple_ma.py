from datetime import datetime, timedelta
from typing import Optional

from trading.models import MarketState, PositionState, Side, TradeSignal
from trading.strategies.simple_ma import SimpleMovingAverageStrategy


SYMBOL = "BTCUSDT"
BASE_TS = datetime(2024, 1, 1, 0, 0, 0)


def _market_state(price: float, idx: int) -> MarketState:
    """Create a deterministic MarketState for the given price/index."""
    return MarketState(
        symbol=SYMBOL,
        timestamp=BASE_TS + timedelta(minutes=idx),
        price=price,
    )


def _run_series(
    strategy: SimpleMovingAverageStrategy,
    prices: list[float],
    position: Optional[PositionState] = None,
) -> Optional[TradeSignal]:
    signal: Optional[TradeSignal] = None
    for idx, price in enumerate(prices):
        signal = strategy.on_market_state(_market_state(price, idx), position)
    return signal


def test_simple_ma_buy_signal_on_cross_above():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="sma-buy",
        symbol=SYMBOL,
        short_window=2,
        long_window=4,
        min_confidence=0.05,
    )
    prices = [100, 101, 102, 104, 120]

    signal = _run_series(strategy, prices)

    assert signal is not None
    assert signal.side is Side.BUY
    assert signal.meta["short_ma"] > signal.meta["long_ma"]


def test_simple_ma_sell_signal_on_cross_below():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="sma-sell",
        symbol=SYMBOL,
        short_window=2,
        long_window=4,
        min_confidence=0.05,
    )
    prices = [120, 119, 118, 117, 100]

    signal = _run_series(strategy, prices)

    assert signal is not None
    assert signal.side is Side.SELL
    assert signal.meta["short_ma"] < signal.meta["long_ma"]


def test_simple_ma_no_signal_when_sideways():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="sma-flat",
        symbol=SYMBOL,
        short_window=2,
        long_window=4,
        min_confidence=0.05,
    )
    prices = [100, 100, 100, 100, 100]

    signal = _run_series(strategy, prices)

    assert signal is None


def test_simple_ma_buy_signal_even_if_already_long():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="sma-long",
        symbol=SYMBOL,
        short_window=2,
        long_window=4,
        min_confidence=0.05,
    )
    long_position = PositionState(
        symbol=SYMBOL,
        side=Side.BUY,
        size=1.0,
        entry_price=100.0,
    )
    prices = [100, 101, 102, 104, 120]

    signal: Optional[TradeSignal] = None
    for idx, price in enumerate(prices):
        # The strategy does not adjust for existing positions, so
        # we pass the long position on every tick to match its design.
        signal = strategy.on_market_state(_market_state(price, idx), long_position)

    assert signal is not None
    assert signal.side is Side.BUY
