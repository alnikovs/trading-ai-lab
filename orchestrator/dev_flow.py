import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List

logger = logging.getLogger("orchestrator.dev_flow")


class DevFlowState(str, Enum):
    IDLE = "idle"
    RUNNING_STEP = "running_step"  # Агент работает над шагом
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class DevFlowSession:
    flow_id: str
    chat_id: str
    flow_type: str = "simple_ma"
    current_step_index: int = 0  # 0-based индекс (для шага 1 будет 0)
    total_steps: int = 3
    state: DevFlowState = DevFlowState.IDLE
    current_agent_id: Optional[str] = None
    context: Dict[str, str] = field(default_factory=dict)
    step_summaries: List[str] = field(default_factory=list)

    def start(self) -> None:
        """Start the DevFlow from step 1."""
        self.current_step_index = 0
        self.state = DevFlowState.RUNNING_STEP

    def build_step_prompt(self) -> str:
        """Return the prompt text for the current step (1-based)."""
        step_num = self.current_step_index + 1  # Convert to 1-based
        step_data = DEVFLOW_SIMPLE_MA_STEPS.get(step_num, {})
        return step_data.get("cursor_task_prompt", "").strip()

    def get_step_title(self) -> str:
        """Return the title for the current step."""
        step_num = self.current_step_index + 1
        step_data = DEVFLOW_SIMPLE_MA_STEPS.get(step_num, {})
        return step_data.get("title", f"Шаг {step_num}")

    def on_step_agent_created(self, agent_id: str) -> None:
        """Bind newly created agent to this session."""
        self.current_agent_id = agent_id

    def on_step_completed(self, summary: Optional[str] = None) -> None:
        """Mark step as completed and wait for user's confirmation."""
        if summary:
            self.step_summaries.append(summary)
        self.state = DevFlowState.AWAITING_CONFIRMATION
        self.current_agent_id = None

    def advance_to_next_step(self) -> None:
        """Advance to the next step and mark as running."""
        if self.current_step_index + 1 < self.total_steps:
            self.current_step_index += 1
            self.state = DevFlowState.RUNNING_STEP
            self.current_agent_id = None
        else:
            # Последний шаг завершён
            self.state = DevFlowState.COMPLETED

    def finish(self) -> None:
        """Mark DevFlow as completed."""
        self.state = DevFlowState.COMPLETED
        self.current_agent_id = None

    def cancel(self) -> None:
        """Cancel DevFlow."""
        self.state = DevFlowState.CANCELLED
        self.current_agent_id = None


class DevFlowStore:
    """In-memory store for DevFlow sessions."""

    _by_id: Dict[str, DevFlowSession] = {}
    _by_chat: Dict[str, DevFlowSession] = {}

    @classmethod
    def create_simple_ma_session(cls, chat_id: str) -> DevFlowSession:
        """Create a new DevFlow session for simple_ma."""
        flow_id = str(uuid.uuid4())
        session = DevFlowSession(
            flow_id=flow_id,
            chat_id=chat_id,
            flow_type="simple_ma",
            total_steps=3,
        )
        cls._by_id[flow_id] = session
        cls._by_chat[chat_id] = session
        logger.info(f"DevFlow: created session flow_id={flow_id}, chat_id={chat_id}, flow_type=simple_ma")
        return session

    @classmethod
    def get_session(cls, chat_id: str) -> Optional[DevFlowSession]:
        """Get active DevFlow session by chat_id."""
        return cls._by_chat.get(chat_id)

    @classmethod
    def save_session(cls, session: DevFlowSession) -> None:
        """Save session (update indexes)."""
        cls._by_id[session.flow_id] = session
        if session.state not in (DevFlowState.COMPLETED, DevFlowState.CANCELLED):
            cls._by_chat[session.chat_id] = session
        else:
            # Remove from chat index if finished
            if session.chat_id in cls._by_chat:
                del cls._by_chat[session.chat_id]

    @classmethod
    def finish_session(cls, chat_id: str) -> None:
        """Finish and remove session."""
        session = cls._by_chat.get(chat_id)
        if session:
            session.finish()
            cls.save_session(session)


def build_step_completed_message(session: DevFlowSession, step_summary: str) -> str:
    """Build human-readable message for completed step."""
    step_num = session.current_step_index + 1
    step_title = session.get_step_title()
    
    # Заголовок
    message = f"✅ Шаг {step_num}/{session.total_steps}: {step_title}\n\n"
    
    # Summary от Cursor
    if step_summary:
        summary_short = step_summary[:300] + "..." if len(step_summary) > 300 else step_summary
        message += f"Результат:\n{summary_short}\n\n"
    
    # Вопрос о продолжении
    if step_num < session.total_steps:
        next_step = step_num + 1
        message += f"Продолжить к шагу {next_step} из {session.total_steps}? (да/нет)"
    else:
        message += "🎉 DevFlow simple_ma завершён! Все шаги выполнены."
    
    return message


# Набор шагов для DevFlow simple_ma
DEVFLOW_SIMPLE_MA_STEPS: Dict[int, Dict[str, str]] = {
    1: {
        "title": "Подготовка стратегии simple_ma",
        "description": "Создать или обновить файл trading/strategies/simple_ma.py с базовым каркасом",
        "cursor_task_prompt": """
Шаг 1/3: Подготовка стратегии simple_ma.

Цель:
- Создать (если нет) или аккуратно обновить файл trading/strategies/simple_ma.py.
- Обеспечить базовый каркас стратегии на основе существующих моделей/интерфейсов в проекте.

Требования:
- Найти базовый класс стратегии (например, BaseStrategy) и использовать его как parent.
- Определить класс SimpleMAStrategy или аналогичный, не ломая существующий код.
- Не добавлять бизнес-логику сигналов, только структуру, параметры и заглушки методов.

Важно:
- Минимизировать побочные изменения в других файлах.
- Если файл уже существует — добавить недостающие части, а не переписывать всё с нуля.
        """,
    },
    2: {
        "title": "Реализация логики Simple Moving Average",
        "description": "Реализовать логику генерации сигналов на основе пересечения двух SMA",
        "cursor_task_prompt": """
Шаг 2/3: Реализация логики простой скользящей средней (Simple Moving Average).

Цель:
- В файле trading/strategies/simple_ma.py реализовать логику генерации сигналов на основе пересечения двух SMA.

Требования:
- Параметры стратегии: fast_window (например, 10), slow_window (например, 50).
- На вход стратегия получает ценовой ряд/кэндлы в формате, который уже принят в проекте (MarketState или аналог).
- На выход — сигналы вида BUY/SELL/FLAT (использовать имеющийся enum Side из trading/models.py, если он есть).
- Логика:
  - Когда fast_SMA пересекает slow_SMA снизу вверх → сигнал BUY.
  - Когда fast_SMA пересекает slow_SMA сверху вниз → сигнал SELL.
  - Иначе → FLAT.

Важно:
- Учитывать, что стратегия может вызываться на стриме данных (on_tick/on_bar).
- Не заниматься исполнением ордеров, только генерацией сигналов.
        """,
    },
    3: {
        "title": "Тесты и валидация",
        "description": "Добавить тесты для стратегии simple_ma",
        "cursor_task_prompt": """
Шаг 3/3: Тесты и минимальная валидация стратегии simple_ma.

Цель:
- Добавить (или обновить) тесты для стратегии простой скользящей средней.

Требования:
- Создать файл тестов (например, tests/test_simple_ma.py или использовать существующий тестовый модуль).
- Покрыть базовые сценарии:
  - fast_SMA выше slow_SMA → сигнал BUY;
  - fast_SMA ниже slow_SMA → сигнал SELL;
  - нет пересечения или одинаковые значения → сигнал FLAT.
- Добавить хотя бы один интеграционный тест, который прогоняет несколько шагов цен и проверяет смену сигналов.

Важно:
- Тесты должны быть достаточно простыми, чтобы их было легко поддерживать.
- Не нужно строить сложный фреймворк — достаточно базового pytest.
        """,
    },
}
