import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from fastapi import FastAPI

from orchestrator.telegram_bot import send_telegram_message, handle_telegram_update


class TestSendTelegramMessage:
    @patch("orchestrator.telegram_bot.TelegramConfig")
    @patch("httpx.AsyncClient")
    async def test_send_short_message_success(self, mock_client_class, mock_config):
        mock_config.TOKEN = "fake_token_123"
        
        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        result = await send_telegram_message("123", "Hello, world!")
        
        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["chat_id"] == 123
        assert call_args[1]["json"]["text"] == "Hello, world!"
    
    @patch("orchestrator.telegram_bot.TelegramConfig")
    @patch("httpx.AsyncClient")
    async def test_send_long_message_splitting(self, mock_client_class, mock_config):
        mock_config.TOKEN = "fake_token_123"
        
        long_text = "A" * 5000
        lines = ["Line " + str(i) + "\n" for i in range(200)]
        long_text = "".join(lines)
        
        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        result = await send_telegram_message("123", long_text)
        
        assert result is True
        assert mock_client.post.call_count >= 1
        for call in mock_client.post.call_args_list:
            text = call[1]["json"]["text"]
            assert len(text) <= 4096
    
    @patch("orchestrator.telegram_bot.TelegramConfig")
    @patch("httpx.AsyncClient")
    async def test_send_message_with_retries(self, mock_client_class, mock_config):
        mock_config.TOKEN = "fake_token_123"
        
        mock_response_error = MagicMock()
        mock_response_error.is_error = True
        mock_response_error.status_code = 500
        
        mock_response_success = MagicMock()
        mock_response_success.is_error = False
        mock_response_success.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(side_effect=[mock_response_error, mock_response_success])
        mock_client_class.return_value = mock_client
        
        result = await send_telegram_message("123", "Test message")
        
        assert result is True
        assert mock_client.post.call_count == 2
    
    @patch("orchestrator.telegram_bot.TelegramConfig")
    @patch("httpx.AsyncClient")
    async def test_send_message_timeout_retry(self, mock_client_class, mock_config):
        mock_config.TOKEN = "fake_token_123"
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client_class.return_value = mock_client
        
        result = await send_telegram_message("123", "Test message")
        
        assert result is False
        # Теперь у нас 3 попытки (основная + 2 ретрая)
        assert mock_client.post.call_count == 3
    
    @patch("orchestrator.telegram_bot.TelegramConfig")
    @patch("httpx.AsyncClient")
    async def test_send_message_request_error_retry(self, mock_client_class, mock_config):
        mock_config.TOKEN = "fake_token_123"
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Network error"))
        mock_client_class.return_value = mock_client
        
        result = await send_telegram_message("123", "Test message")
        
        assert result is False
        # Теперь у нас 3 попытки (основная + 2 ретрая)
        assert mock_client.post.call_count == 3
    
    @patch("orchestrator.telegram_bot.TelegramConfig")
    async def test_send_message_invalid_user_id(self, mock_config):
        mock_config.TOKEN = "fake_token_123"
        
        result = await send_telegram_message("invalid", "Test message")
        
        assert result is False
    
    @patch("orchestrator.telegram_bot.TelegramConfig")
    async def test_send_message_no_token(self, mock_config):
        mock_config.TOKEN = None
        
        result = await send_telegram_message("123", "Test message")
        
        assert result is False


class TestHandleTelegramUpdate:
    @pytest.fixture
    def fake_app(self):
        app = FastAPI()
        app.state.config = {"model": "gpt-4"}
        app.state.openai_client = None
        app.state.dev_agent_store = MagicMock()
        return app
    
    @patch("orchestrator.telegram_bot.send_telegram_message")
    async def test_handle_start_command(self, mock_send, fake_app):
        mock_send.return_value = True
        
        await handle_telegram_update(fake_app, "123", "/start")
        
        mock_send.assert_called_once()
        call_text = mock_send.call_args[0][1]
        assert "Привет" in call_text or "trading-бот" in call_text
    
    @patch("orchestrator.telegram_bot.send_telegram_message")
    async def test_handle_help_command(self, mock_send, fake_app):
        mock_send.return_value = True
        
        await handle_telegram_update(fake_app, "123", "/help")
        
        mock_send.assert_called_once()
        call_text = mock_send.call_args[0][1]
        assert "Команды" in call_text or "help" in call_text.lower()
    
    @patch("orchestrator.telegram_bot.send_telegram_message")
    async def test_handle_ping_command(self, mock_send, fake_app):
        mock_send.return_value = True
        
        await handle_telegram_update(fake_app, "123", "ping")
        
        mock_send.assert_called_once()
        assert mock_send.call_args[0][1] == "pong 🟢"
    
    @patch("orchestrator.telegram_bot.send_telegram_message")
    async def test_handle_status_command(self, mock_send, fake_app):
        mock_send.return_value = True
        
        await handle_telegram_update(fake_app, "123", "/status")
        
        mock_send.assert_called_once()
        call_text = mock_send.call_args[0][1]
        assert "Статус оркестратора" in call_text
    
    @patch("orchestrator.telegram_bot.send_telegram_message")
    async def test_handle_echo_command(self, mock_send, fake_app):
        mock_send.return_value = True
        
        await handle_telegram_update(fake_app, "123", "echo hello world")
        
        mock_send.assert_called_once()
        assert mock_send.call_args[0][1] == "hello world"
    
    @patch("orchestrator.telegram_bot.send_telegram_message")
    @patch("orchestrator.telegram_bot.handle_message")
    async def test_handle_normal_message_reply_only(self, mock_handle_message, mock_send, fake_app):
        mock_send.return_value = True
        
        class FakeAction:
            action = "reply_only"
            reply_text = "Hi from router"
            dev_task = None
            dev_agent_id = None
        
        mock_handle_message.return_value = FakeAction()
        
        await handle_telegram_update(fake_app, "123", "Hello")
        
        mock_send.assert_called_once()
        assert mock_send.call_args[0][1] == "Hi from router"
    
    @patch("orchestrator.telegram_bot.send_telegram_message")
    @patch("orchestrator.telegram_bot.create_cursor_agent")
    @patch("orchestrator.telegram_bot.handle_message")
    async def test_handle_start_dev_agent(
        self,
        mock_handle_message,
        mock_create_agent,
        mock_send,
        fake_app,
    ):
        mock_send.return_value = True
        
        from orchestrator.cursor_client import CursorAgentCreateResult
        
        mock_create_agent.return_value = CursorAgentCreateResult(
            id="agent-123",
            status="running"
        )
        
        class FakeAction:
            action = "start_dev_agent"
            reply_text = None
            dev_task = "Test task"
            dev_agent_id = None
        
        mock_handle_message.return_value = FakeAction()
        
        await handle_telegram_update(fake_app, "123", "Test message")
        
        assert fake_app.state.dev_agent_store.register.called
        mock_send.assert_called()
        call_text = mock_send.call_args[0][1]
        assert "Dev Agent" in call_text or "agent-123" in call_text
    
    @patch("orchestrator.telegram_bot.send_telegram_message")
    @patch("orchestrator.telegram_bot.get_cursor_agent_status")
    @patch("orchestrator.telegram_bot.handle_message")
    async def test_handle_check_dev_status(
        self,
        mock_handle_message,
        mock_get_status,
        mock_send,
        fake_app,
    ):
        mock_send.return_value = True
        mock_get_status.return_value = {
            "status": "done",
            "url": "https://cursor.com/agent-123",
            "pr_url": "https://github.com/pr/123"
        }
        
        class FakeAction:
            action = "check_dev_status"
            reply_text = None
            dev_task = None
            dev_agent_id = "agent-123"
        
        mock_handle_message.return_value = FakeAction()
        
        await handle_telegram_update(fake_app, "123", "Check status")
        
        mock_send.assert_called_once()
        call_text = mock_send.call_args[0][1]
        assert "agent-123" in call_text
        assert "done" in call_text
    
    @patch("orchestrator.telegram_bot.send_telegram_message")
    @patch("orchestrator.telegram_bot.handle_message")
    async def test_handle_noop_action(self, mock_handle_message, mock_send, fake_app):
        class FakeAction:
            action = "noop"
            reply_text = None
            dev_task = None
            dev_agent_id = None
        
        mock_handle_message.return_value = FakeAction()
        
        await handle_telegram_update(fake_app, "123", "Some message")
        
        assert not mock_send.called

