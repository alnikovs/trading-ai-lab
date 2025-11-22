from datetime import datetime, timedelta

from trading.models import MarketState, Side
from trading.strategies.simple_ma import SimpleMovingAverageStrategy


def _feed_prices(strategy: SimpleMovingAverageStrategy, prices: list[float]):
    """Helper: sequentially feed prices into the strategy and collect emitted signals."""
    base_ts = datetime(2024, 1, 1)
    signals = []
    for idx, price in enumerate(prices):
        market_state = MarketState(
            symbol=strategy.symbol,
            timestamp=base_ts + timedelta(minutes=idx),
            price=price,
        )
        signal = strategy.on_market_state(market_state, position=None)
        if signal is not None:
            signals.append(signal)
    return signals


def test_simple_ma_emits_buy_when_short_above_long():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="simple_ma",
        symbol="BTCUSDT",
        short_window=2,
        long_window=3,
    )

    signals = _feed_prices(strategy, [100.0, 100.0, 120.0])

    assert signals, "strategy should emit a signal once both windows are populated"
    last_signal = signals[-1]
    assert last_signal.side == Side.BUY
    assert last_signal.meta["short_ma"] > last_signal.meta["long_ma"]


def test_simple_ma_emits_sell_when_short_below_long():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="simple_ma",
        symbol="BTCUSDT",
        short_window=2,
        long_window=3,
    )

    signals = _feed_prices(strategy, [120.0, 120.0, 90.0])

    assert signals, "strategy should emit a signal once both windows are populated"
    last_signal = signals[-1]
    assert last_signal.side == Side.SELL
    assert last_signal.meta["short_ma"] < last_signal.meta["long_ma"]


def test_simple_ma_returns_none_when_averages_equal():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="simple_ma",
        symbol="BTCUSDT",
        short_window=2,
        long_window=3,
    )

    signals = _feed_prices(strategy, [100.0, 100.0, 100.0])

    assert signals == []


def test_simple_ma_signal_sequence_changes_over_time():
    strategy = SimpleMovingAverageStrategy(
        strategy_id="simple_ma",
        symbol="BTCUSDT",
        short_window=2,
        long_window=3,
    )

    prices = [100.0, 100.0, 120.0, 80.0, 70.0]
    signals = _feed_prices(strategy, prices)
    sides = [signal.side for signal in signals]

    assert Side.BUY in sides
    assert Side.SELL in sides

    deduped_sides = []
    for side in sides:
        if not deduped_sides or deduped_sides[-1] != side:
            deduped_sides.append(side)

    assert deduped_sides[0] == Side.BUY
    assert Side.SELL in deduped_sides[1:], "expected a transition from BUY to SELL"
