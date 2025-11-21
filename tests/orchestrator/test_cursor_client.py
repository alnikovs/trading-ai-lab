import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from orchestrator.cursor_client import create_cursor_agent, get_cursor_agent_status, CursorAgentCreateResult


class TestCreateCursorAgent:
    @patch("orchestrator.cursor_client.CursorConfig")
    @patch("httpx.AsyncClient")
    async def test_create_cursor_agent_success(self, mock_client_class, mock_config):
        mock_config.API_KEY = "fake_api_key"
        mock_config.BASE_URL = "https://api.cursor.com"
        mock_config.REPOSITORY = "test/repo"
        mock_config.BASE_REF = "main"
        mock_config.WEBHOOK_URL = "https://example.com/webhook"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "agent-1",
            "status": "running",
            "url": "https://cursor.com/agent-1",
            "pr_url": "https://github.com/pr/1",
            "branch_name": "test-branch"
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        result = await create_cursor_agent(
            task_text="Test task",
            auto_create_pr=True,
            branch_name="test-branch"
        )
        
        assert isinstance(result, CursorAgentCreateResult)
        assert result.id == "agent-1"
        assert result.status == "running"
        assert result.url == "https://cursor.com/agent-1"
        assert result.pr_url == "https://github.com/pr/1"
        assert result.branch_name == "test-branch"
        
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["prompt"]["text"] == "Test task"
        assert payload["source"]["repository"] == "test/repo"
        assert payload["source"]["ref"] == "main"
        assert payload["target"]["autoCreatePr"] is True
        assert payload["target"]["branchName"] == "test-branch"
        assert payload["webhook"]["url"] == "https://example.com/webhook"
    
    @patch("orchestrator.cursor_client.CursorConfig")
    @patch("httpx.AsyncClient")
    async def test_create_cursor_agent_without_webhook(self, mock_client_class, mock_config):
        mock_config.API_KEY = "fake_api_key"
        mock_config.BASE_URL = "https://api.cursor.com"
        mock_config.REPOSITORY = "test/repo"
        mock_config.BASE_REF = "main"
        mock_config.WEBHOOK_URL = None
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "agent-1",
            "status": "running"
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        result = await create_cursor_agent(task_text="Test task")
        
        assert result.id == "agent-1"
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert "webhook" not in payload
    
    @patch("orchestrator.cursor_client.CursorConfig")
    async def test_create_cursor_agent_invalid_webhook_url(self, mock_config):
        mock_config.API_KEY = "fake_api_key"
        mock_config.REPOSITORY = "test/repo"
        mock_config.WEBHOOK_URL = "ftp://invalid-url"
        
        with pytest.raises(ValueError, match="Invalid CURSOR_WEBHOOK_URL"):
            await create_cursor_agent(task_text="Test task")
    
    @patch("orchestrator.cursor_client.CursorConfig")
    async def test_create_cursor_agent_missing_api_key(self, mock_config):
        mock_config.API_KEY = None
        mock_config.REPOSITORY = "test/repo"
        
        with pytest.raises(ValueError, match="CURSOR_API_KEY not configured"):
            await create_cursor_agent(task_text="Test task")
    
    @patch("orchestrator.cursor_client.CursorConfig")
    async def test_create_cursor_agent_missing_repository(self, mock_config):
        mock_config.API_KEY = "fake_api_key"
        mock_config.REPOSITORY = None
        
        with pytest.raises(ValueError, match="CURSOR_REPOSITORY not configured"):
            await create_cursor_agent(task_text="Test task")
    
    @patch("orchestrator.cursor_client.CursorConfig")
    @patch("httpx.AsyncClient")
    async def test_create_cursor_agent_http_error(self, mock_client_class, mock_config):
        mock_config.API_KEY = "fake_api_key"
        mock_config.BASE_URL = "https://api.cursor.com"
        mock_config.REPOSITORY = "test/repo"
        mock_config.BASE_REF = "main"
        mock_config.WEBHOOK_URL = None
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        error = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
        mock_response.raise_for_status.side_effect = error
        
        with pytest.raises(RuntimeError) as exc_info:
            await create_cursor_agent(task_text="Test task")
        
        assert "HTTP 500" in str(exc_info.value)
        assert hasattr(exc_info.value, "status_code")
        assert exc_info.value.status_code == 500
    
    @patch("orchestrator.cursor_client.CursorConfig")
    @patch("httpx.AsyncClient")
    async def test_create_cursor_agent_network_error(self, mock_client_class, mock_config):
        mock_config.API_KEY = "fake_api_key"
        mock_config.BASE_URL = "https://api.cursor.com"
        mock_config.REPOSITORY = "test/repo"
        mock_config.BASE_REF = "main"
        mock_config.WEBHOOK_URL = None
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Network error"))
        mock_client_class.return_value = mock_client
        
        with pytest.raises(RuntimeError, match="Request failed"):
            await create_cursor_agent(task_text="Test task")


class TestGetCursorAgentStatus:
    @patch("orchestrator.cursor_client.CursorConfig")
    @patch("httpx.AsyncClient")
    async def test_get_cursor_agent_status_success(self, mock_client_class, mock_config):
        mock_config.API_KEY = "fake_api_key"
        mock_config.BASE_URL = "https://api.cursor.com"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "agent-1",
            "status": "done",
            "url": "https://cursor.com/agent-1",
            "pr_url": "https://github.com/pr/1"
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        result = await get_cursor_agent_status("agent-1")
        
        assert result["id"] == "agent-1"
        assert result["status"] == "done"
        assert result["url"] == "https://cursor.com/agent-1"
        
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "agent-1" in call_args[0][0]
    
    @patch("orchestrator.cursor_client.CursorConfig")
    async def test_get_cursor_agent_status_missing_api_key(self, mock_config):
        mock_config.API_KEY = None
        
        with pytest.raises(ValueError, match="CURSOR_API_KEY not configured"):
            await get_cursor_agent_status("agent-1")
    
    @patch("orchestrator.cursor_client.CursorConfig")
    @patch("httpx.AsyncClient")
    async def test_get_cursor_agent_status_http_error(self, mock_client_class, mock_config):
        mock_config.API_KEY = "fake_api_key"
        mock_config.BASE_URL = "https://api.cursor.com"
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        error = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
        mock_response.raise_for_status.side_effect = error
        
        with pytest.raises(RuntimeError) as exc_info:
            await get_cursor_agent_status("agent-1")
        
        assert "HTTP 404" in str(exc_info.value)
        assert hasattr(exc_info.value, "status_code")
        assert exc_info.value.status_code == 404
    
    @patch("orchestrator.cursor_client.CursorConfig")
    @patch("httpx.AsyncClient")
    async def test_get_cursor_agent_status_network_error(self, mock_client_class, mock_config):
        mock_config.API_KEY = "fake_api_key"
        mock_config.BASE_URL = "https://api.cursor.com"
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Network error"))
        mock_client_class.return_value = mock_client
        
        with pytest.raises(RuntimeError, match="Request failed"):
            await get_cursor_agent_status("agent-1")

