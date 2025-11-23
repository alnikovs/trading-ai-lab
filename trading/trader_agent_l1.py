from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol

from trading.models import MarketState, PositionState, TradeSignal
from trading.risk_interface import RiskEngineInterface
from trading.strategies.base import Strategy
from trading.strategies.simple_ma import SimpleMovingAverageStrategy

StrategyConfig = Dict[str, Any]
StrategyFactory = Callable[[StrategyConfig], Strategy]


def _simple_ma_factory(config: StrategyConfig) -> Strategy:
    """
    Build a SimpleMovingAverageStrategy from a generic config payload.
    Expected config keys:
        - strategy_id: unique identifier per strategy instance
        - symbol: instrument symbol
        - params (optional): dict with overrides for short_window, long_window, min_confidence
    """
    params = config.get("params", {}) or {}
    return SimpleMovingAverageStrategy(
        strategy_id=config["strategy_id"],
        symbol=config["symbol"],
        short_window=params.get("short_window", 10),
        long_window=params.get("long_window", 30),
        min_confidence=params.get("min_confidence", 0.6),
    )


STRATEGY_REGISTRY: Dict[str, StrategyFactory] = {
    "simple_ma": _simple_ma_factory,
}


class ExchangeAdapter(Protocol):
    """
    Протокол для адаптера биржи.
    Конкретная реализация может жить, например, в hyperliquid_adapter
    или другом модуле. Здесь определяем только интерфейс.
    """

    def get_positions(self) -> Dict[str, PositionState]:
        """
        Вернуть текущее состояние позиций по символам.
        Ключ словаря — symbol.
        """
        ...

    def execute_signals(self, signals: Iterable[TradeSignal]) -> None:
        """
        Превратить сигналы в реальные ордера и отправить на биржу.
        Детали исполнения скрыты внутри адаптера.
        """
        ...


@dataclass
class TraderAgentL1:
    """
    Базовый трейдер-агент первого уровня.

    Его ответственность:
    - собрать сигналы от стратегий;
    - прогнать их через risk engine;
    - отдать в адаптер биржи для исполнения.

    Важно: здесь нет ML, RL и сложных решений — только
    простой, детерминированный пайплайн.
    """

    strategies: List[Strategy]
    risk_engine: RiskEngineInterface
    exchange_adapter: ExchangeAdapter

    @classmethod
    def from_strategy_configs(
        cls,
        strategy_configs: Iterable[StrategyConfig],
        risk_engine: RiskEngineInterface,
        exchange_adapter: ExchangeAdapter,
    ) -> "TraderAgentL1":
        """
        Build an agent by instantiating strategies referenced by name.
        Each config must declare:
            - name: registry key (e.g. "simple_ma")
            - strategy_id
            - symbol
            - params (optional dict passed to the factory)
        """
        strategies: List[Strategy] = []
        for config in strategy_configs:
            strategy_name = config.get("name")
            if not strategy_name:
                raise ValueError("strategy config must include 'name'")
            factory = STRATEGY_REGISTRY.get(strategy_name)
            if factory is None:
                raise ValueError(f"unknown strategy name '{strategy_name}'")
            missing_fields = [field for field in ("strategy_id", "symbol") if field not in config]
            if missing_fields:
                raise ValueError(
                    f"strategy config '{strategy_name}' missing required fields: {', '.join(missing_fields)}"
                )
            strategies.append(factory(config))
        return cls(
            strategies=strategies,
            risk_engine=risk_engine,
            exchange_adapter=exchange_adapter,
        )

    def _build_position_map(self) -> Dict[str, PositionState]:
        return dict(self.exchange_adapter.get_positions())

    def on_market_state(self, market_state: MarketState) -> List[TradeSignal]:
        """
        Один цикл обработки рыночного состояния.

        1. получаем позиции;
        2. пробрасываем market_state во все стратегии по этому символу;
        3. собираем сырые сигналы;
        4. прогоняем через risk engine;
        5. отдаём на исполнение через exchange_adapter.

        Возвращает список сигналов, которые прошли риск-фильтр.
        """
        positions_map = self._build_position_map()
        symbol = market_state.symbol
        position: Optional[PositionState] = positions_map.get(symbol)

        raw_signals: List[TradeSignal] = []

        for strategy in self.strategies:
            if strategy.symbol != symbol:
                # стратегия работает по своему символу — можно позже сделать мультисимвольные
                continue
            signal = self._generate_signal(strategy, market_state, position)
            if signal is not None:
                raw_signals.append(signal)

        if not raw_signals:
            return []

        filtered_signals = self.risk_engine.filter_signals(
            signals=raw_signals,
            positions=positions_map.values(),
        )

        if filtered_signals:
            self.exchange_adapter.execute_signals(filtered_signals)

        return filtered_signals

    @staticmethod
    def _generate_signal(
        strategy: Strategy,
        market_state: MarketState,
        position: Optional[PositionState],
    ) -> Optional[TradeSignal]:
        """
        Call a strategy's `generate_signal` method when available, otherwise fall back to
        the older `on_market_state` name. This keeps backward compatibility while
        allowing DevFlow steps to prefer generate_signal explicitly.
        """
        generate_signal: Optional[Callable[[MarketState, Optional[PositionState]], Optional[TradeSignal]]] = getattr(
            strategy, "generate_signal", None
        )
        if callable(generate_signal):
            return generate_signal(market_state=market_state, position=position)
        return strategy.on_market_state(market_state, position)
