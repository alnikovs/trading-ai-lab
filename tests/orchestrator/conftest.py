import os
import pytest
from fastapi.testclient import TestClient

os.environ["TESTING"] = "1"

from orchestrator.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_telegram_messages():
    messages = []
    
    async def record_message(user_id: str, text: str) -> bool:
        messages.append({"user_id": user_id, "text": text})
        return True
    
    return messages, record_message


@pytest.fixture
def in_memory_commands():
    data = {"commands": [], "results": []}
    return data

