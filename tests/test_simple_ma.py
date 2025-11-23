from datetime import datetime, timedelta

from trading.models import MarketState, PositionState, Side
from trading.strategies.simple_ma import SimpleMovingAverageStrategy


BASE_TIME = datetime(2024, 1, 1, 0, 0, 0)


def _market_state(price: float, idx: int) -> MarketState:
    return MarketState(
        symbol="TEST",
        timestamp=BASE_TIME + timedelta(minutes=idx),
        price=price,
    )


def test_simple_ma_emits_buy_signal_on_bullish_cross():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="sma",
        symbol="TEST",
        short_window=3,
        long_window=5,
        min_confidence=0.05,
    )
    prices = [100, 102, 104, 106, 140]

    signal = None
    for idx, price in enumerate(prices):
        signal = strategy.on_market_state(_market_state(price, idx), position=None)

    assert signal is not None
    assert signal.side == Side.BUY
    assert signal.symbol == "TEST"


def test_simple_ma_emits_sell_signal_on_bearish_cross():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="sma",
        symbol="TEST",
        short_window=3,
        long_window=5,
        min_confidence=0.05,
    )
    prices = [140, 130, 120, 110, 90]

    signal = None
    for idx, price in enumerate(prices):
        signal = strategy.on_market_state(_market_state(price, idx), position=None)

    assert signal is not None
    assert signal.side == Side.SELL


def test_simple_ma_returns_none_without_cross():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="sma",
        symbol="TEST",
        short_window=3,
        long_window=5,
        min_confidence=0.05,
    )
    prices = [100, 100, 100, 100, 100]

    signal = None
    for idx, price in enumerate(prices):
        signal = strategy.on_market_state(_market_state(price, idx), position=None)

    assert signal is None


def test_simple_ma_ignores_existing_long_position_on_repeated_buy():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="sma",
        symbol="TEST",
        short_window=3,
        long_window=5,
        min_confidence=0.05,
    )
    prices = [100, 102, 104, 106, 140]
    position = PositionState(symbol="TEST", side=Side.BUY, size=1.0, entry_price=100)

    signal = None
    for idx, price in enumerate(prices):
        current_position = position if idx == len(prices) - 1 else None
        signal = strategy.on_market_state(_market_state(price, idx), position=current_position)

    assert signal is not None
    assert signal.side == Side.BUY
