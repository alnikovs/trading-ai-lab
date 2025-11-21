# Test Suite for Trading AI Lab Orchestrator

## Overview

This test suite provides comprehensive pytest-based tests for the orchestrator service. All tests are hermetic and do not make real HTTP requests or API calls.

## Structure

```
tests/
├── __init__.py
├── orchestrator/
│   ├── __init__.py
│   ├── conftest.py              # Test fixtures and configuration
│   ├── test_main_endpoints.py   # Tests for FastAPI endpoints
│   ├── test_telegram_bot.py     # Tests for Telegram bot functionality
│   ├── test_memory_store.py     # Tests for memory store operations
│   └── test_cursor_client.py    # Tests for Cursor API client
└── README.md
```

## Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/orchestrator/test_main_endpoints.py

# Run with verbose output
pytest -v

# Run specific test class
pytest tests/orchestrator/test_main_endpoints.py::TestHealthEndpoint
```

## Test Coverage

### test_main_endpoints.py
- GET /health
- POST /telegram/webhook
- POST /chat (with various response types)
- POST /from-chatgpt/command
- GET /for-cursor/commands
- POST /from-cursor/result
- GET /for-chatgpt/results
- GET /tasks, POST /tasks/add, POST /tasks/update
- POST /dev/agents, GET /dev/agents/{agent_id}

### test_telegram_bot.py
- send_telegram_message (short/long messages, retries, errors)
- handle_telegram_update (commands, normal messages, dev agent actions)

### test_memory_store.py
- load_config, save_messages, load_message_history
- load_ai_contract, load_project_summary
- load_tasks, save_tasks
- load_commands, save_commands, load_recent_results, find_command_by_id

### test_cursor_client.py
- create_cursor_agent (success, errors, validation)
- get_cursor_agent_status (success, errors)

## Test Mode

Tests run in TESTING mode (set via `TESTING=1` environment variable). In this mode:
- No real OpenAI API key required
- No real config files loaded
- Minimal app.state initialization
- All external calls are mocked

## Dependencies

Tests require:
- pytest
- fastapi (for TestClient)
- httpx (for mocking HTTP calls)
- unittest.mock (for mocking)

Add to requirements.txt if not present:
```
pytest
pytest-asyncio
```

