from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Protocol

from trading.models import MarketState, PositionState, TradeSignal
from trading.risk_interface import RiskEngineInterface
from trading.strategies.base import Strategy


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
            signal = strategy.generate_signal(market_state, position)
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
