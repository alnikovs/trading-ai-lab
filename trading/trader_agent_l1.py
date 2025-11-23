from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol

from trading.models import MarketState, PositionState, TradeSignal
from trading.risk_interface import RiskEngineInterface
from trading.strategies.base import Strategy
from trading.strategies.simple_ma import SimpleMovingAverageStrategy as SimpleMAStrategy


StrategyBuilder = Callable[["StrategyConfig"], Strategy]


@dataclass(frozen=True)
class StrategyConfig:
    """
    Lightweight strategy description that can be turned into a Strategy instance.
    """

    name: str
    strategy_id: str
    symbol: str
    params: Dict[str, Any] = field(default_factory=dict)


def _build_simple_ma_strategy(config: StrategyConfig) -> Strategy:
    return SimpleMAStrategy(
        strategy_id=config.strategy_id,
        symbol=config.symbol,
        **config.params,
    )


_DEFAULT_STRATEGY_REGISTRY: Dict[str, StrategyBuilder] = {
    "simple_ma": _build_simple_ma_strategy,
}


def build_strategy_from_config(
    config: StrategyConfig,
    registry: Optional[Dict[str, StrategyBuilder]] = None,
) -> Strategy:
    """
    Build a concrete Strategy instance from a StrategyConfig.
    """
    if registry:
        merged_registry = _DEFAULT_STRATEGY_REGISTRY.copy()
        merged_registry.update(registry)
    else:
        merged_registry = _DEFAULT_STRATEGY_REGISTRY

    try:
        builder = merged_registry[config.name]
    except KeyError as exc:
        known = ", ".join(sorted(merged_registry.keys())) or "none"
        raise ValueError(
            f"Unknown strategy '{config.name}'. Known strategies: {known}"
        ) from exc
    return builder(config)


def build_strategies_from_configs(
    configs: Iterable[StrategyConfig],
    registry: Optional[Dict[str, StrategyBuilder]] = None,
) -> List[Strategy]:
    """
    Helper to build a list of strategies from declarative configs.
    """
    return [build_strategy_from_config(config, registry) for config in configs]


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
        strategy_registry: Optional[Dict[str, StrategyBuilder]] = None,
    ) -> "TraderAgentL1":
        """
        Convenience constructor that wires strategies by their declarative name.

        Allows selecting e.g. the simple moving average strategy via the
        `"simple_ma"` identifier and passing custom parameters through `params`.
        """
        strategies = build_strategies_from_configs(
            strategy_configs=strategy_configs,
            registry=strategy_registry,
        )
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
            signal = strategy.on_market_state(market_state, position)
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
