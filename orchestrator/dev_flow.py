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
        "id": "simple_ma_impl",
        "title": "Implement simple MA strategy core logic",
        "description": (
            "Implement a working simple moving average (SMA) trading strategy in "
            "trading/strategies/simple_ma.py with signal generation logic."
        ),
        "cursor_task_prompt": """
GOAL:

Implement a working simple moving average (SMA) trading strategy in:

- trading/strategies/simple_ma.py



Context:

- Core types are defined in trading/models.py (Side, MarketState, PositionState, TradeSignal).

- The base strategy interface is defined in trading/strategies/base.py.

- This project is research-only and used for simulations/backtesting, not for real-money trading.



Requirements:

1) In `trading/strategies/simple_ma.py`, implement or refactor a class like `SimpleMAStrategy` that:

   - Inherits from the common base strategy interface in `trading/strategies/base.py`.

   - Accepts configuration (e.g. SMA window length) via __init__ or a config object.

   - Exposes a method such as:

     `generate_signal(market_state: MarketState, position_state: PositionState) -> TradeSignal`.



2) Trading logic:

   - Compute a simple moving average over the last N close prices (N = window).

   - If the latest price crosses ABOVE the SMA and we are FLAT or SHORT -> return a BUY signal.

   - If the latest price crosses BELOW the SMA and we are FLAT or LONG -> return a SELL signal.

   - Otherwise -> return a FLAT/no-trade signal.



3) Code quality:

   - Use type hints.

   - Add a clear module-level docstring and class/method docstrings.

   - Keep the strategy deterministic and easy to test.



4) Non-empty diff requirement:

   - You MUST actually modify `trading/strategies/simple_ma.py`.

   - Even if something is already implemented, improve or refactor it so that the final diff is not empty.



Constraints:

- Do NOT wire this directly to any real-money exchange.

- Do NOT provide financial advice; focus purely on strategy logic.



Output:

- Apply code changes to the repository.

- Then reply with a short summary of what you changed and which files you touched.
        """.strip(),
    },
    {
        "id": "simple_ma_tests",
        "title": "Add tests for simple MA strategy",
        "description": (
            "Create pytest tests for the simple moving average strategy in "
            "tests/test_simple_ma.py covering BUY/SELL/FLAT scenarios."
        ),
        "cursor_task_prompt": """
GOAL:

Create pytest tests for the simple moving average strategy implemented in:

- trading/strategies/simple_ma.py



Requirements:

1) Create or update:

   - tests/test_simple_ma.py



2) Test scenarios (at least these):

   - A price series where the last price clearly crosses ABOVE the SMA -> expect a BUY signal.

   - A price series where the last price clearly crosses BELOW the SMA -> expect a SELL signal.

   - A sideways/no-crossover scenario -> expect FLAT/no-trade signal.

   - A scenario where we already hold a LONG position and there is another BUY crossover -> behavior should match the strategy's design (e.g. either FLAT or some specific logic); assert whatever is implemented.



3) Tests should:

   - Import MarketState, PositionState, Side, TradeSignal from `trading/models.py`.

   - Import the strategy class from `trading/strategies/simple_ma.py`.

   - Build explicit deterministic price series and market states in the test code.



4) Non-empty diff requirement:

   - You MUST create or meaningfully update `tests/test_simple_ma.py` so that the tests are useful and would pass if the strategy is correctly implemented.



Output:

- Apply changes to the test file(s).

- Then reply with a short summary describing the tests you added.
        """.strip(),
    },
    {
        "id": "simple_ma_integration",
        "title": "Integrate simple MA strategy into trader agent",
        "description": (
            "Integrate the simple moving average strategy into the trader agent "
            "so it can be selected and used in trading/trader_agent_l1.py."
        ),
        "cursor_task_prompt": """
GOAL:

Integrate the simple moving average strategy into the trader agent so it can be selected and used.



Files to touch:

- trading/trader_agent_l1.py

- (Optionally) imports in trading/strategies/simple_ma.py if needed.



Requirements:

1) In `trading/trader_agent_l1.py`:

   - Ensure there is a clear way to construct `SimpleMAStrategy` by name or configuration.

   - For example, extend a strategy factory or mapping so that the name "simple_ma"

     maps to `SimpleMAStrategy` with configurable parameters (e.g. window length).



2) Behavior:

   - The trader agent should be able to accept "simple_ma" as a strategy choice

     and call the strategy's `generate_signal(...)` method to produce TradeSignal objects.



3) Keep integration minimal:

   - Do NOT add real-money exchange wiring here.

   - Focus on in-process orchestration and strategy selection.



4) Non-empty diff requirement:

   - You MUST modify `trading/trader_agent_l1.py` (and related imports if needed) with real code changes.

   - Even if some integration already exists, refactor/improve it so there is a meaningful non-empty diff.



Output:

- Apply the integration changes.

- Then reply with a short summary of how you wired the strategy into the trader agent.
        """.strip(),
    },
]
