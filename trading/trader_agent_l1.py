from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Union

from trading.models import MarketState, PositionState, TradeSignal
from trading.risk_interface import RiskEngineInterface
from trading.strategies.base import Strategy
from trading.strategies.simple_ma import SimpleMovingAverageStrategy as SimpleMAStrategy


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


StrategyFactory = Callable[["StrategyConfig"], Strategy]
StrategyConfigLike = Union["StrategyConfig", Dict[str, Any]]


@dataclass(frozen=True)
class StrategyConfig:
    """
    Normalized description of a strategy that can be instantiated
    through the registry (e.g. simple_ma).
    """

    name: str
    strategy_id: str
    symbol: str
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "StrategyConfig":
        """
        Allow light-weight dict configs such as:
        {"name": "simple_ma", "strategy_id": "ma_btc", "symbol": "BTCUSDT", "short_window": 5}
        """
        if "name" not in raw:
            raise ValueError("Strategy config dict must include 'name'")
        if "symbol" not in raw:
            raise ValueError("Strategy config dict must include 'symbol'")

        strategy_id = raw.get("strategy_id") or raw.get("id")
        if not strategy_id:
            raise ValueError("Strategy config dict must include 'strategy_id' or 'id'")

        params: Dict[str, Any] = dict(raw.get("params") or {})
        for key, value in raw.items():
            if key in {"name", "symbol", "strategy_id", "id", "params"}:
                continue
            params[key] = value

        return cls(
            name=str(raw["name"]),
            strategy_id=strategy_id,
            symbol=str(raw["symbol"]),
            params=params,
        )


def _normalize_strategy_config(config: StrategyConfigLike) -> StrategyConfig:
    if isinstance(config, StrategyConfig):
        return config
    if isinstance(config, dict):
        return StrategyConfig.from_dict(config)
    raise TypeError(f"Unsupported strategy config type: {type(config)!r}")


def _build_simple_ma_strategy(config: StrategyConfig) -> Strategy:
    allowed_params = {"short_window", "long_window", "min_confidence"}
    extra_params = set(config.params) - allowed_params
    if extra_params:
        raise ValueError(
            f"Unsupported params for simple_ma ({sorted(extra_params)}). "
            f"Allowed parameters: {sorted(allowed_params)}"
        )

    kwargs = {key: config.params[key] for key in allowed_params if key in config.params}
    return SimpleMAStrategy(
        strategy_id=config.strategy_id,
        symbol=config.symbol,
        **kwargs,
    )


STRATEGY_FACTORY_REGISTRY: Dict[str, StrategyFactory] = {
    "simple_ma": _build_simple_ma_strategy,
}


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
        strategy_configs: Iterable[StrategyConfigLike],
        risk_engine: RiskEngineInterface,
        exchange_adapter: ExchangeAdapter,
    ) -> "TraderAgentL1":
        """
        Convenience constructor that turns lightweight configs into concrete strategies.
        Current registry supports 'simple_ma'.
        """
        strategies = [
            cls._build_strategy(_normalize_strategy_config(config))
            for config in strategy_configs
        ]
        return cls(
            strategies=strategies,
            risk_engine=risk_engine,
            exchange_adapter=exchange_adapter,
        )

    @classmethod
    def register_strategy_factory(cls, name: str, factory: StrategyFactory) -> None:
        """
        Allow runtime extension of available strategies (mainly for tests).
        """
        STRATEGY_FACTORY_REGISTRY[name] = factory

    @staticmethod
    def _build_strategy(config: StrategyConfig) -> Strategy:
        try:
            factory = STRATEGY_FACTORY_REGISTRY[config.name]
        except KeyError as exc:
            raise ValueError(f"Unknown strategy '{config.name}'") from exc
        return factory(config)

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
        Call a strategy's signal generator. Prefers `generate_signal` if the
        strategy exposes it, falls back to legacy `on_market_state`.
        """
        generate_signal = getattr(strategy, "generate_signal", None)
        if callable(generate_signal):
            return generate_signal(market_state, position)
        return strategy.on_market_state(market_state, position)
