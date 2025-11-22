import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List, Any

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
        step_num = self.current_step_index + 1  # Convert to 1-based (1, 2, 3)
        if 0 <= self.current_step_index < len(DEVFLOW_SIMPLE_MA_STEPS):
            step_data = DEVFLOW_SIMPLE_MA_STEPS[self.current_step_index]
            return step_data.get("cursor_task_prompt", "").strip()
        return ""

    def get_step_title(self) -> str:
        """Return the title for the current step."""
        if 0 <= self.current_step_index < len(DEVFLOW_SIMPLE_MA_STEPS):
            step_data = DEVFLOW_SIMPLE_MA_STEPS[self.current_step_index]
            return step_data.get("title", f"Шаг {self.current_step_index + 1}")
        return f"Шаг {self.current_step_index + 1}"

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
DEVFLOW_SIMPLE_MA_STEPS: List[Dict[str, Any]] = [
    {
        "id": "prepare_simple_ma_structure",
        "title": "Подготовка стратегии simple_ma",
        "description": (
            "Создать и/или привести в порядок структуру стратегии Simple Moving Average (SimpleMAStrategy): "
            "конфиг, класс стратегии, базовые проверки и каркас методов, чтобы следующий шаг мог "
            "сосредоточиться только на торговой логике."
        ),
        "cursor_task_prompt": """
You are an AI developer working on the AI Quant Fund trading bot project.

This is **DevFlow simple_ma – Step 1/3: Prepare simple_ma strategy structure**.

Goal of this step:
- Ensure that `trading/strategies/simple_ma.py` contains a clean, production-ready skeleton for a Simple Moving Average strategy (SimpleMAStrategy) with a separate immutable config and basic validation, ready for signal logic implementation in the next step.

Context:
- Repo structure (key files):
  - `trading/strategies/base.py`  — base strategy interfaces and common logic
  - `trading/models.py`          — MarketState, PositionState, TradeSignal, Side, etc.
  - `trading/strategies/simple_ma.py` — the file for SimpleMAStrategy implementation

IMPORTANT: All user-facing messages in Telegram must remain in Russian. Do NOT change Telegram texts or DevFlow user messages to English.

Requirements for this step (you MUST do real code changes, not just planning):

1) **Strategy config**
   - Define a config dataclass for the strategy, e.g. `SimpleMAConfig`, with at least:
     - `short_window: int`
     - `long_window: int`
     - `min_confidence: float` (0.0–1.0 range)
   - Provide validation logic so that:
     - `short_window >= 1`
     - `long_window > short_window`
     - `0.0 <= min_confidence <= 1.0`
   - Make config immutable (frozen dataclass) and suitable to be passed around safely.

2) **Strategy class skeleton**
   - Implement or refactor `SimpleMAStrategy` in `trading/strategies/simple_ma.py` so that it:
     - Inherits from the appropriate base (check `trading/strategies/base.py`, e.g. `Strategy` / `BaseStrategy`).
     - Accepts the config object in the constructor and stores it.
     - Has a clear internal state for price history (you may initialize it here, logic will be filled in Step 2).
     - Exposes public methods required by the base class (e.g. `on_market_state`, `reset`, etc.) as working stubs.

3) **Validation and error handling**
   - Ensure invalid config values raise clear exceptions early (e.g. ValueError with informative messages).
   - Keep the code simple and explicit; avoid premature optimization.

4) **Code quality and style**
   - Follow the existing code style in the project.
   - Add type hints where appropriate.
   - Add docstrings to the config and the strategy class, briefly explaining what they do.

5) **Tests / sanity checks**
   - If there are existing tests that touch `simple_ma`, make sure they still import and run.
   - If no tests exist yet, at least ensure that the module imports cleanly and that constructing `SimpleMAConfig` and `SimpleMAStrategy` works without runtime errors for valid configs.

VERY IMPORTANT:
- This step MUST produce real code changes in `trading/strategies/simple_ma.py` (and related files if needed), not just a "plan".
- Do NOT leave the summary as "No code changes were made". Make the best reasonable implementation based on the current project structure.
- Do NOT modify the language of Telegram messages; they must stay Russian.
- If you need to make small supportive changes in other modules (e.g. imports, minor helpers) to keep things consistent — do it.

At the end of this step:
- The project should import without errors.
- `SimpleMAConfig` and `SimpleMAStrategy` should exist and form a clean, validated skeleton ready for SMA logic in Step 2.
- In your summary, briefly describe:
  - What exactly was changed (files, classes, functions).
  - Any assumptions you made.
  - Any TODOs you intentionally left for the next steps.
        """.strip(),
    },
    {
        "id": "implement_simple_ma_logic",
        "title": "Реализация логики Simple Moving Average",
        "description": (
            "Реализовать торговую логику SMA в SimpleMAStrategy: вести окно цен, считать короткую и длинную "
            "средние, генерировать сигналы BUY/SELL/FLAT с учётом min_confidence и текущего состояния позиции."
        ),
        "cursor_task_prompt": """
You are an AI developer working on the AI Quant Fund trading bot project.

This is **DevFlow simple_ma – Step 2/3: Implement Simple Moving Average trading logic**.

Goal of this step:
- Implement the actual SMA-based trading logic inside `SimpleMAStrategy` in `trading/strategies/simple_ma.py`, using the config and skeleton prepared in Step 1.

Context:
- Use the existing project models:
  - `MarketState` and `PositionState` from `trading/models.py`
  - `TradeSignal` and `Side` (BUY / SELL / FLAT)
- The strategy should:
  - Maintain a rolling history of recent prices.
  - Compute short and long moving averages.
  - Emit trading signals based on the crossover and confidence.

IMPORTANT: All user-facing messages in Telegram must remain in Russian. Do NOT change Telegram texts or DevFlow user messages to English.

Requirements (real code changes, not just planning):

1) **Price history and state**
   - Store the last N prices needed to compute both short and long windows.
   - Ensure that until there is enough data (less than `long_window` prices), the strategy returns `None` / FLAT (depending on project conventions) and does NOT produce invalid signals.
   - Provide a `reset()` method that clears internal state.

2) **SMA computation**
   - Implement helpers (private methods) to:
     - Ingest a new price from `MarketState` (e.g. mid-price, last trade price, or a selected field — choose a reasonable one and document it).
     - Compute short and long simple moving averages over the history.
   - Make sure the code is numerically simple and easy to read.

3) **Signal generation**
   - Implement logic that:
     - Emits a BUY signal when the short MA crosses above the long MA with sufficient confidence.
     - Emits a SELL signal when the short MA crosses below the long MA with sufficient confidence.
     - Otherwise returns FLAT / no signal.
   - Use `min_confidence` from the config to modulate the confidence value in `TradeSignal`.
   - Incorporate `PositionState` so that:
     - You don't repeatedly emit the same signal on every tick if the position is already aligned with the signal.
     - You can choose to be conservative (e.g. avoid flipping too often). Document any design choices.

4) **Integration with `on_market_state`**
   - `on_market_state` should:
     - Take `MarketState` and `PositionState`.
     - Update internal state with the new price.
     - Decide whether to emit a `TradeSignal` or return `None` / FLAT.
   - Make sure types and return values are consistent with the base strategy interface and with `TradeSignal` from `trading/models.py`.

5) **Basic tests / self-check**
   - If tests for this strategy already exist, adjust the implementation so that they pass.
   - If tests do not yet exist, you may add simple sanity checks or minimal tests (but the full testing will be done in Step 3).
   - At minimum, verify that:
     - The strategy can be instantiated with a valid config.
     - Feeding a sequence of prices that clearly exhibits a crossover produces at least one BUY or SELL signal as expected (you can test this in code inside the module or via a small helper).

IMPORTANT:
- This step MUST modify `trading/strategies/simple_ma.py` to contain a working first version of SMA trading logic.
- Avoid leaving TODO-only stubs. Make a reasonable, consistent implementation that future agents can refine.
- Do NOT modify user-facing Telegram texts; they must stay Russian.
- In your summary, clearly list:
  - The exact decision rule for BUY/SELL/FLAT.
  - How you computed confidence.
  - Any assumptions or limitations (e.g. which price from MarketState is used).
        """.strip(),
    },
    {
        "id": "test_and_validate_simple_ma",
        "title": "Тесты и валидация simple_ma",
        "description": (
            "Написать и/или доработать unit-тесты для SimpleMAStrategy: сценарии BUY/SELL/FLAT, проверки валидации "
            "конфига, поведения при недостатке данных. Запустить pytest и убедиться, что всё зелёное."
        ),
        "cursor_task_prompt": """
You are an AI developer working on the AI Quant Fund trading bot project.

This is **DevFlow simple_ma – Step 3/3: Tests and validation for SimpleMAStrategy**.

Goal of this step:
- Add or refine unit tests for `SimpleMAStrategy` so that the SMA strategy is covered by meaningful, passing tests.

Context:
- Strategy implementation: `trading/strategies/simple_ma.py`
- Models: `trading/models.py`
- Existing tests: check `tests/` and `tests/trading/` to see how other strategies or components are tested.

IMPORTANT: All user-facing messages in Telegram must remain in Russian. Do NOT change Telegram texts or DevFlow user messages to English.

Requirements:

1) **Test file and structure**
   - Create or update a test module, e.g.:
     - `tests/trading/strategies/test_simple_ma.py`
   - Follow the existing project test style (pytest is expected).
   - Import `SimpleMAConfig`, `SimpleMAStrategy`, `MarketState`, `PositionState`, `Side`, `TradeSignal` as needed.

2) **Positive scenarios (signals)**
   - Add tests that cover at least:
     - BUY scenario: a price series where the short SMA clearly crosses above the long SMA and a BUY signal is expected.
     - SELL scenario: a price series where the short SMA clearly crosses below the long SMA and a SELL signal is expected.
     - FLAT / no-signal scenario: a price series with no strong crossover or where the position is already aligned and no new signal should be emitted.
   - Check not just the `Side`, but also that the confidence is in a reasonable range and respects `min_confidence`.

3) **Config validation tests**
   - Add tests that validate creation of `SimpleMAConfig`:
     - Invalid short/long window combinations should raise an exception.
     - Invalid `min_confidence` (e.g. < 0 or > 1) should raise an exception.
   - Make sure error messages are understandable.

4) **Edge cases**
   - Test behavior when there is not enough history to compute both SMAs:
     - The strategy should not crash.
     - It should return `None` / FLAT (depending on your implementation) until enough data is collected.
   - Optionally, test behavior when prices are constant or very noisy.

5) **Running tests**
   - Run the full test suite with `pytest` from the project root (or at least the tests for this strategy).
   - Fix any failures related to `simple_ma` implementation or tests.
   - Do NOT skip failing tests silently; fix the root causes where possible.

VERY IMPORTANT:
- This step MUST create or update real test files.
- Do NOT leave this as "planning tests only"; the goal is to have tests that actually run and pass.
- Do NOT modify Telegram user-facing texts; they must stay Russian.
- In your summary, briefly include:
  - The path to the test file(s) you added/modified.
  - A short description of each main test scenario.
  - The result of `pytest` (e.g. "pytest passed for all tests", or what is still failing and why, if anything remains).

At the end of this step:
- `SimpleMAStrategy` should be covered by meaningful tests.
- `pytest` should pass for at least the new tests; ideally for the whole project if feasible.
        """.strip(),
    },
]
