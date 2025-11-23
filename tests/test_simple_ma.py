from datetime import datetime, timedelta
from typing import Iterable, Optional

from trading.models import MarketState, PositionState, Side
from trading.strategies.simple_ma import SimpleMovingAverageStrategy

BASE_TS = datetime(2024, 1, 1, 0, 0, 0)


def _make_market_state(price: float, step: int) -> MarketState:
    return MarketState(
        symbol="BTCUSDT",
        price=price,
        timestamp=BASE_TS + timedelta(minutes=step),
    )


def _run_strategy(
    strategy: SimpleMovingAverageStrategy,
    prices: Iterable[float],
    position: Optional[PositionState] = None,
):
    signal = None
    for idx, price in enumerate(prices):
        signal = strategy.on_market_state(_make_market_state(price, idx), position)
    return signal


def _build_strategy() -> SimpleMovingAverageStrategy:
    return SimpleMovingAverageStrategy(
        strategy_id="sma-test",
        symbol="BTCUSDT",
        short_window=2,
        long_window=4,
        min_confidence=0.1,
    )


def test_simple_ma_buy_signal_on_bullish_cross():
    strategy = _build_strategy()
    prices = [100.0, 99.0, 101.0, 105.0, 110.0]

    signal = _run_strategy(strategy, prices)

    assert signal is not None
    assert signal.side is Side.BUY
    assert signal.meta["short_ma"] > signal.meta["long_ma"]
    assert signal.confidence >= 0.1


def test_simple_ma_sell_signal_on_bearish_cross():
    strategy = _build_strategy()
    prices = [110.0, 108.0, 105.0, 102.0, 98.0]

    signal = _run_strategy(strategy, prices)

    assert signal is not None
    assert signal.side is Side.SELL
    assert signal.meta["short_ma"] < signal.meta["long_ma"]


def test_simple_ma_returns_none_without_crossover():
    strategy = _build_strategy()
    prices = [100.0, 100.0, 100.0, 100.0, 100.0]

    signal = _run_strategy(strategy, prices)

    assert signal is None


def test_simple_ma_buy_signal_even_with_existing_long_position():
    strategy = _build_strategy()
    existing_position = PositionState(
        symbol="BTCUSDT",
        side=Side.BUY,
        size=1.0,
        entry_price=99.0,
    )
    prices = [100.0, 99.0, 101.0, 105.0, 110.0]

    signal = _run_strategy(strategy, prices, position=existing_position)

    assert signal is not None
    assert signal.side is Side.BUY
    assert signal.meta["short_ma"] > signal.meta["long_ma"]
