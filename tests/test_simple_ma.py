from datetime import datetime, timedelta
from typing import Iterable, Optional

from trading.models import MarketState, PositionState, Side, TradeSignal
from trading.strategies.simple_ma import SimpleMAStrategy

BASE_TS = datetime(2024, 1, 1, 0, 0, 0)
SYMBOL = "BTCUSDT"


def _make_market_state(price: float, step: int) -> MarketState:
    return MarketState(
        symbol=SYMBOL,
        price=price,
        timestamp=BASE_TS + timedelta(minutes=step),
    )


def _run_strategy(
    strategy: SimpleMAStrategy,
    prices: Iterable[float],
    position: Optional[PositionState] = None,
) -> Optional[TradeSignal]:
    signal: Optional[TradeSignal] = None
    for idx, price in enumerate(prices):
        signal = strategy.on_market_state(_make_market_state(price, idx), position)
    return signal


def _build_strategy(window: int = 3, min_confidence: float = 0.05) -> SimpleMAStrategy:
    return SimpleMAStrategy(
        strategy_id="sma-test",
        symbol=SYMBOL,
        window=window,
        trade_size=1.0,
        min_confidence=min_confidence,
    )


def test_simple_ma_buy_signal_on_cross_above():
    strategy = _build_strategy()
    prices = [100.0, 99.0, 98.0, 110.0]

    signal = _run_strategy(strategy, prices)

    assert isinstance(signal, TradeSignal)
    assert signal.side is Side.BUY
    assert signal.meta["price"] > signal.meta["sma"]


def test_simple_ma_sell_signal_on_cross_below():
    strategy = _build_strategy()
    prices = [100.0, 101.0, 103.0, 90.0]

    signal = _run_strategy(strategy, prices)

    assert isinstance(signal, TradeSignal)
    assert signal.side is Side.SELL
    assert signal.meta["price"] < signal.meta["sma"]


def test_simple_ma_returns_none_without_crossover():
    strategy = _build_strategy()
    prices = [100.0, 101.0, 102.0, 103.0]

    signal = _run_strategy(strategy, prices)

    assert signal is None


def test_simple_ma_skips_buy_signal_when_already_long():
    strategy = _build_strategy()
    existing_position = PositionState(
        symbol=SYMBOL,
        side=Side.BUY,
        size=1.0,
        entry_price=99.0,
    )
    prices = [100.0, 99.0, 98.0, 110.0]

    signal = _run_strategy(strategy, prices, position=existing_position)

    assert signal is None
