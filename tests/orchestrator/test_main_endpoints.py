import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    def test_health_endpoint(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        # Проверяем наличие хотя бы одного временного поля (timestamp или time_utc)
        assert "timestamp" in data or "time_utc" in data


class TestTelegramWebhook:
    @patch("orchestrator.main.handle_telegram_update")
    def test_telegram_webhook_with_message(self, mock_handle, client: TestClient):
        async def mock_handle_update(*args, **kwargs):
            return None
        
        mock_handle.side_effect = mock_handle_update
        
        payload = {
            "message": {
                "chat": {"id": 123},
                "text": "ping",
            }
        }
        
        response = client.post("/telegram/webhook", json=payload)
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        
        mock_handle.assert_called_once()
        args, kwargs = mock_handle.call_args
        # chat_id и text передаются как позиционные аргументы
        assert args[1] == "123"
        assert args[2] == "ping"
        # raw_payload передается как именованный аргумент
        assert kwargs["raw_payload"] == payload
    
    def test_telegram_webhook_no_message(self, client: TestClient):
        payload = {"update_id": 123}
        
        response = client.post("/telegram/webhook", json=payload)
        assert response.status_code == 200
        assert response.json() == {"ok": True}


class TestChatEndpoint:
    @patch("orchestrator.main.save_messages")
    @patch("orchestrator.main.load_message_history")
    @patch("orchestrator.main.load_recent_results")
    @patch("orchestrator.main.load_tasks")
    @patch("orchestrator.main.load_project_summary")
    @patch("orchestrator.main.load_ai_contract")
    def test_chat_reply_user(
        self,
        mock_contract,
        mock_summary,
        mock_tasks,
        mock_results,
        mock_history,
        mock_save,
        client: TestClient,
    ):
        mock_contract.return_value = ""
        mock_summary.return_value = ""
        mock_tasks.return_value = {"tasks": []}
        mock_results.return_value = []
        mock_history.return_value = []
        
        class FakeChoices:
            def __init__(self, content: str):
                self.message = type("msg", (), {"content": content})()
        
        class FakeCompletion:
            def __init__(self, content: str):
                self.choices = [FakeChoices(content)]
        
        class FakeOpenAIClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(model, messages):
                        return FakeCompletion('{"type": "reply_user", "message": "Hello from AI"}')
        
        client.app.state.openai_client = FakeOpenAIClient()
        client.app.state.config = {"model": "gpt-4"}
        
        response = client.post(
            "/chat",
            json={"user_id": "test_user", "message": "Hello"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "Hello from AI"
        assert data.get("command_id") is None
    
    @patch("orchestrator.main.save_messages")
    @patch("orchestrator.main.load_message_history")
    @patch("orchestrator.main.load_recent_results")
    @patch("orchestrator.main.load_tasks")
    @patch("orchestrator.main.load_project_summary")
    @patch("orchestrator.main.load_ai_contract")
    @patch("orchestrator.main.add_command")
    def test_chat_call_cursor(
        self,
        mock_add_command,
        mock_contract,
        mock_summary,
        mock_tasks,
        mock_results,
        mock_history,
        mock_save,
        client: TestClient,
    ):
        mock_contract.return_value = ""
        mock_summary.return_value = ""
        mock_tasks.return_value = {"tasks": []}
        mock_results.return_value = []
        mock_history.return_value = []
        mock_add_command.return_value = "cmd-test-123"
        
        class FakeChoices:
            def __init__(self, content: str):
                self.message = type("msg", (), {"content": content})()
        
        class FakeCompletion:
            def __init__(self, content: str):
                self.choices = [FakeChoices(content)]
        
        class FakeOpenAIClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(model, messages):
                        return FakeCompletion('{"type": "call_cursor", "task_id": "T123", "command": {"prompt": "Do something with Cursor"}}')
        
        client.app.state.openai_client = FakeOpenAIClient()
        client.app.state.config = {"model": "gpt-4"}
        
        response = client.post(
            "/chat",
            json={"user_id": "test_user", "message": "Create a file"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "Cursor" in data["reply"]
        assert data["command_id"] == "cmd-test-123"
        mock_add_command.assert_called_once()
    
    @patch("orchestrator.main.save_messages")
    @patch("orchestrator.main.load_message_history")
    @patch("orchestrator.main.load_recent_results")
    @patch("orchestrator.main.load_tasks")
    @patch("orchestrator.main.load_project_summary")
    @patch("orchestrator.main.load_ai_contract")
    def test_chat_plain_text_response(
        self,
        mock_contract,
        mock_summary,
        mock_tasks,
        mock_results,
        mock_history,
        mock_save,
        client: TestClient,
    ):
        mock_contract.return_value = ""
        mock_summary.return_value = ""
        mock_tasks.return_value = {"tasks": []}
        mock_results.return_value = []
        mock_history.return_value = []
        
        class FakeChoices:
            def __init__(self, content: str):
                self.message = type("msg", (), {"content": content})()
        
        class FakeCompletion:
            def __init__(self, content: str):
                self.choices = [FakeChoices(content)]
        
        class FakeOpenAIClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(model, messages):
                        return FakeCompletion("Just plain text response")
        
        client.app.state.openai_client = FakeOpenAIClient()
        client.app.state.config = {"model": "gpt-4"}
        
        response = client.post(
            "/chat",
            json={"user_id": "test_user", "message": "Hello"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "Just plain text response"


class TestFromChatGPTCommand:
    @patch("orchestrator.main.add_command")
    def test_receive_command(self, mock_add_command, client: TestClient):
        mock_add_command.return_value = "cmd-test-1"
        
        response = client.post(
            "/from-chatgpt/command",
            json={"task_id": "T001", "command": {"prompt": "do something"}}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["command_id"] == "cmd-test-1"


class TestForCursorCommands:
    def test_get_pending_commands(self, client: TestClient):
        command1 = {
            "id": "cmd-1",
            "prompt": "Test prompt 1",
            "user_id": "user1",
            "timestamp": "2024-01-01T00:00:00Z"
        }
        command2 = {
            "id": "cmd-2",
            "prompt": "Test prompt 2",
            "user_id": "user2",
            "timestamp": "2024-01-01T00:00:01Z"
        }
        
        client.app.state.pending_cursor_commands = [command1, command2]
        
        response = client.get("/for-cursor/commands")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["commands"]) == 2
        assert data["commands"][0]["id"] == "cmd-1"
        assert data["commands"][1]["id"] == "cmd-2"
        
        assert len(client.app.state.pending_cursor_commands) == 0
    
    def test_get_pending_commands_empty(self, client: TestClient):
        client.app.state.pending_cursor_commands = []
        
        response = client.get("/for-cursor/commands")
        
        assert response.status_code == 200
        data = response.json()
        assert data["commands"] == []


class TestFromCursorResult:
    @patch("orchestrator.main.send_telegram_message")
    @patch("orchestrator.main.save_commands")
    @patch("orchestrator.main.load_commands")
    def test_receive_result_success(
        self,
        mock_load,
        mock_save,
        mock_send,
        client: TestClient,
    ):
        async def mock_send_message(*args, **kwargs):
            return True
        
        mock_send.side_effect = mock_send_message
        
        command_data = {
            "commands": [
                {
                    "id": "cmd-123",
                    "task_id": "T001",
                    "user_id": "user123",
                    "prompt": "Test command"
                }
            ],
            "results": []
        }
        mock_load.return_value = command_data
        
        response = client.post(
            "/from-cursor/result",
            json={
                "command_id": "cmd-123",
                "status": "ok",
                "result": {
                    "diff": "some diff",
                    "notes": "some notes",
                    "message": "Done"
                }
            }
        )
        
        assert response.status_code == 200
        assert response.json()["ok"] is True
        
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == "user123"
        assert "Cursor выполнил задачу" in call_args[0][1]
        
        assert mock_save.called
        saved_data = mock_save.call_args[0][0]
        assert len(saved_data["results"]) == 1
        assert saved_data["results"][0]["command_id"] == "cmd-123"
        assert saved_data["results"][0]["status"] == "ok"
    
    @patch("orchestrator.main.send_telegram_message")
    @patch("orchestrator.main.save_commands")
    @patch("orchestrator.main.load_commands")
    def test_receive_result_error(
        self,
        mock_load,
        mock_save,
        mock_send,
        client: TestClient,
    ):
        async def mock_send_message(*args, **kwargs):
            return True
        
        mock_send.side_effect = mock_send_message
        
        command_data = {
            "commands": [
                {
                    "id": "cmd-123",
                    "task_id": "T001",
                    "user_id": "user123",
                }
            ],
            "results": []
        }
        mock_load.return_value = command_data
        
        response = client.post(
            "/from-cursor/result",
            json={
                "command_id": "cmd-123",
                "status": "error",
                "result": {"error": "Some error message"}
            }
        )
        
        assert response.status_code == 200
        assert response.json()["ok"] is True
        
        call_args = mock_send.call_args
        assert "выполнил задачу с ошибкой" in call_args[0][1]
        assert "Some error message" in call_args[0][1]
        
        saved_data = mock_save.call_args[0][0]
        assert saved_data["results"][0]["status"] == "error"
    
    @patch("orchestrator.main.send_telegram_message")
    @patch("orchestrator.main.load_commands")
    def test_receive_result_unknown_command(
        self,
        mock_load,
        mock_send,
        client: TestClient,
    ):
        mock_load.return_value = {"commands": [], "results": []}
        client.app.state.pending_cursor_commands = []
        
        async def mock_send_message(*args, **kwargs):
            return True
        
        mock_send.side_effect = mock_send_message
        
        response = client.post(
            "/from-cursor/result",
            json={
                "command_id": "unknown-cmd",
                "status": "ok",
                "result": {}
            }
        )
        
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert not mock_send.called


class TestForChatGPTResults:
    @patch("orchestrator.main.load_commands")
    def test_get_results_all(self, mock_load, client: TestClient):
        mock_load.return_value = {
            "results": [
                {"command_id": "cmd-1", "task_id": "T001", "status": "ok"},
                {"command_id": "cmd-2", "task_id": "T002", "status": "ok"},
                {"command_id": "cmd-3", "task_id": "T001", "status": "ok"},
            ]
        }
        
        response = client.get("/for-chatgpt/results")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 3
    
    @patch("orchestrator.main.load_commands")
    def test_get_results_filtered(self, mock_load, client: TestClient):
        mock_load.return_value = {
            "results": [
                {"command_id": "cmd-1", "task_id": "T001", "status": "ok"},
                {"command_id": "cmd-2", "task_id": "T002", "status": "ok"},
                {"command_id": "cmd-3", "task_id": "T001", "status": "ok"},
            ]
        }
        
        response = client.get("/for-chatgpt/results?task_id=T001")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert all(r["task_id"] == "T001" for r in data["results"])


class TestTasksEndpoints:
    @patch("orchestrator.main.save_tasks")
    @patch("orchestrator.main.load_tasks")
    def test_get_tasks(self, mock_load, mock_save, client: TestClient):
        tasks_data = {
            "tasks": [
                {"id": "T001", "title": "Task 1", "status": "open"},
                {"id": "T002", "title": "Task 2", "status": "done"},
            ]
        }
        mock_load.return_value = tasks_data
        
        response = client.get("/tasks")
        
        assert response.status_code == 200
        assert response.json() == tasks_data
    
    @patch("orchestrator.main.save_tasks")
    @patch("orchestrator.main.load_tasks")
    def test_add_task(self, mock_load, mock_save, client: TestClient):
        mock_load.return_value = {
            "tasks": [
                {"id": "T001", "title": "Task 1", "status": "open"},
                {"id": "T005", "title": "Task 5", "status": "open"},
            ]
        }
        
        response = client.post(
            "/tasks/add",
            json={"title": "New Task", "details": "Task details"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        # Задача возвращается в поле "task"
        task = data["task"]
        assert task["id"] == "T006"
        assert task["title"] == "New Task"
        assert task["status"] == "open"
        assert "created_at" in task
        
        assert mock_save.called
    
    @patch("orchestrator.main.save_tasks")
    @patch("orchestrator.main.load_tasks")
    def test_update_task_success(self, mock_load, mock_save, client: TestClient):
        mock_load.return_value = {
            "tasks": [
                {"id": "T001", "title": "Task 1", "status": "open"},
            ]
        }
        
        response = client.post(
            "/tasks/update",
            json={"id": "T001", "status": "in_progress"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        # Задача возвращается в поле "task"
        task = data["task"]
        assert task["id"] == "T001"
        assert task["status"] == "in_progress"
        assert "updated_at" in task
    
    @patch("orchestrator.main.load_tasks")
    def test_update_task_invalid_status(self, mock_load, client: TestClient):
        mock_load.return_value = {
            "tasks": [
                {"id": "T001", "title": "Task 1", "status": "open"},
            ]
        }
        
        response = client.post(
            "/tasks/update",
            json={"id": "T001", "status": "invalid_status"}
        )
        
        assert response.status_code == 400
    
    @patch("orchestrator.main.load_tasks")
    def test_update_task_not_found(self, mock_load, client: TestClient):
        mock_load.return_value = {"tasks": []}
        
        response = client.post(
            "/tasks/update",
            json={"id": "T999", "status": "done"}
        )
        
        assert response.status_code == 404


class TestDevAgentsEndpoints:
    @patch("orchestrator.main.create_cursor_agent")
    def test_create_dev_agent_success(self, mock_create, client: TestClient):
        from orchestrator.cursor_client import CursorAgentCreateResult
        
        async def mock_create_agent(*args, **kwargs):
            return CursorAgentCreateResult(
                id="agent-123",
                status="running",
                url="https://cursor.com/agent-123",
                pr_url="https://github.com/pr/123",
                branch_name="test-branch"
            )
        
        mock_create.side_effect = mock_create_agent
        
        response = client.post(
            "/dev/agents",
            json={
                "task": "Test task",
                "auto_create_pr": True,
                "branch_name": "test-branch"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-123"
        assert data["status"] == "running"
        assert data["url"] == "https://cursor.com/agent-123"
        assert data["pr_url"] == "https://github.com/pr/123"
        assert data["branch_name"] == "test-branch"
    
    @patch("orchestrator.main.create_cursor_agent")
    def test_create_dev_agent_value_error(self, mock_create, client: TestClient):
        async def mock_create_agent(*args, **kwargs):
            raise ValueError("CURSOR_API_KEY not configured")
        
        mock_create.side_effect = mock_create_agent
        
        response = client.post(
            "/dev/agents",
            json={"task": "Test task"}
        )
        
        assert response.status_code == 500
        assert "CURSOR_API_KEY" in response.json()["detail"]
    
    @patch("orchestrator.main.create_cursor_agent")
    def test_create_dev_agent_runtime_error(self, mock_create, client: TestClient):
        async def mock_create_agent(*args, **kwargs):
            error = RuntimeError("HTTP 500: Internal Server Error")
            error.status_code = 500
            error.response_text = "Internal Server Error"
            raise error
        
        mock_create.side_effect = mock_create_agent
        
        response = client.post(
            "/dev/agents",
            json={"task": "Test task"}
        )
        
        assert response.status_code == 500
    
    @patch("orchestrator.main.get_cursor_agent_status")
    def test_get_dev_agent_status_success(self, mock_get_status, client: TestClient):
        async def mock_get_agent_status(*args, **kwargs):
            return {
                "id": "agent-123",
                "status": "done",
                "url": "https://cursor.com/agent-123",
                "pr_url": "https://github.com/pr/123",
                "summary": "Task completed"
            }
        
        mock_get_status.side_effect = mock_get_agent_status
        
        response = client.get("/dev/agents/agent-123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent-123"
        assert data["status"] == "done"
        assert data["url"] == "https://cursor.com/agent-123"
        assert data["pr_url"] == "https://github.com/pr/123"
        assert data["summary"] == "Task completed"
    
    @patch("orchestrator.main.get_cursor_agent_status")
    def test_get_dev_agent_status_error(self, mock_get_status, client: TestClient):
        async def mock_get_agent_status(*args, **kwargs):
            error = RuntimeError("HTTP 404: Not Found")
            error.status_code = 404
            error.response_text = "Not Found"
            raise error
        
        mock_get_status.side_effect = mock_get_agent_status
        
        response = client.get("/dev/agents/agent-123")
        
        assert response.status_code == 404

