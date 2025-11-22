from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import time
import threading


@dataclass
class DevAgentRecord:
    agent_id: str
    chat_id: str
    original_text: str
    dev_task: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    # DevFlow fields
    is_devflow: bool = False
    flow_type: Optional[str] = None
    step_index: Optional[int] = None


class DevAgentStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_agent_id: Dict[str, DevAgentRecord] = {}

    def register(
        self,
        agent_id: str,
        chat_id: str,
        original_text: str,
        dev_task: Optional[str] = None,
        is_devflow: bool = False,
        flow_type: Optional[str] = None,
        step_index: Optional[int] = None,
    ) -> None:
        with self._lock:
            self._by_agent_id[agent_id] = DevAgentRecord(
                agent_id=agent_id,
                chat_id=chat_id,
                original_text=original_text,
                dev_task=dev_task,
                is_devflow=is_devflow,
                flow_type=flow_type,
                step_index=step_index,
            )

    def get(self, agent_id: str) -> Optional[DevAgentRecord]:
        with self._lock:
            return self._by_agent_id.get(agent_id)


_store = DevAgentStore()


def get_dev_agent_store() -> DevAgentStore:
    return _store

