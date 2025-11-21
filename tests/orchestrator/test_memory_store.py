import json
import pytest
from pathlib import Path
from unittest.mock import patch

from orchestrator import memory_store


class TestLoadConfig:
    def test_load_config_exists(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"model": "gpt-4", "temperature": 0.7}')
        
        monkeypatch.setattr(memory_store, "CONFIG_DIR", tmp_path)
        
        result = memory_store.load_config()
        
        assert result["model"] == "gpt-4"
        assert result["temperature"] == 0.7
    
    def test_load_config_example_exists(self, tmp_path, monkeypatch):
        example_file = tmp_path / "config.example.json"
        example_file.write_text('{"model": "gpt-3.5-turbo"}')
        
        monkeypatch.setattr(memory_store, "CONFIG_DIR", tmp_path)
        
        result = memory_store.load_config()
        
        assert result["model"] == "gpt-3.5-turbo"
    
    def test_load_config_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "CONFIG_DIR", tmp_path)
        
        with pytest.raises(FileNotFoundError):
            memory_store.load_config()
    
    def test_load_config_invalid_json(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"invalid": json}')
        
        monkeypatch.setattr(memory_store, "CONFIG_DIR", tmp_path)
        
        with pytest.raises(json.JSONDecodeError):
            memory_store.load_config()


class TestMessageHistory:
    def test_save_and_load_messages(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        memory_store.save_messages("user1", "Hello", "Hi there")
        memory_store.save_messages("user1", "How are you?", "I'm fine")
        
        history = memory_store.load_message_history("user1", max_messages=10)
        
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Hi there"
    
    def test_load_message_history_max_messages(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        for i in range(10):
            memory_store.save_messages("user2", f"Message {i}", f"Reply {i}")
        
        history = memory_store.load_message_history("user2", max_messages=5)
        
        assert len(history) == 5
    
    def test_load_message_history_invalid_json_line(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        messages_file = tmp_path / "messages_user3.jsonl"
        messages_file.write_text(
            '{"role": "user", "content": "Valid"}\n'
            'invalid json line\n'
            '{"role": "assistant", "content": "Valid reply"}\n'
        )
        
        history = memory_store.load_message_history("user3")
        
        assert len(history) == 2
    
    def test_load_message_history_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        history = memory_store.load_message_history("nonexistent")
        
        assert history == []


class TestAIContract:
    def test_load_ai_contract_not_exists(self):
        result = memory_store.load_ai_contract()
        
        assert isinstance(result, str)


class TestProjectSummary:
    def test_load_project_summary_exists(self, tmp_path, monkeypatch):
        summary_file = tmp_path / "project_summary.md"
        summary_file.write_text("# Project Summary\n\nDescription")
        
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        result = memory_store.load_project_summary()
        
        assert "Project Summary" in result
        assert "Description" in result
    
    def test_load_project_summary_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        result = memory_store.load_project_summary()
        
        assert result == ""


class TestTasks:
    def test_save_and_load_tasks(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        tasks_data = {
            "tasks": [
                {"id": "T001", "title": "Task 1", "status": "open"},
                {"id": "T002", "title": "Task 2", "status": "done"},
            ]
        }
        
        memory_store.save_tasks(tasks_data)
        result = memory_store.load_tasks()
        
        assert len(result["tasks"]) == 2
        assert result["tasks"][0]["id"] == "T001"
        assert result["tasks"][1]["id"] == "T002"
    
    def test_load_tasks_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        result = memory_store.load_tasks()
        
        assert result == {"tasks": []}
    
    def test_load_tasks_invalid_structure(self, tmp_path, monkeypatch):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text('["invalid", "structure"]')
        
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        result = memory_store.load_tasks()
        
        assert result == {"tasks": []}


class TestCommands:
    def test_save_and_load_commands(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        commands_data = {
            "commands": [
                {"id": "cmd-1", "prompt": "Do something"},
            ],
            "results": [
                {"command_id": "cmd-1", "status": "ok"},
            ]
        }
        
        memory_store.save_commands(commands_data)
        result = memory_store.load_commands()
        
        assert len(result["commands"]) == 1
        assert len(result["results"]) == 1
        assert result["commands"][0]["id"] == "cmd-1"
    
    def test_load_commands_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        result = memory_store.load_commands()
        
        assert result == {"commands": [], "results": []}
    
    def test_load_commands_missing_keys(self, tmp_path, monkeypatch):
        commands_file = tmp_path / "commands.json"
        commands_file.write_text('{"commands": []}')
        
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        result = memory_store.load_commands()
        
        assert "commands" in result
        assert "results" in result
    
    def test_load_recent_results(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        commands_data = {
            "commands": [],
            "results": [
                {"command_id": "cmd-1", "status": "ok"},
                {"command_id": "cmd-2", "status": "ok"},
                {"command_id": "cmd-3", "status": "ok"},
                {"command_id": "cmd-4", "status": "ok"},
                {"command_id": "cmd-5", "status": "ok"},
            ]
        }
        
        memory_store.save_commands(commands_data)
        result = memory_store.load_recent_results(max_results=3)
        
        assert len(result) == 3
        assert result[0]["command_id"] == "cmd-3"
        assert result[-1]["command_id"] == "cmd-5"
    
    def test_find_command_by_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_store, "MEMORY_DIR", tmp_path)
        
        commands_data = {
            "commands": [
                {"id": "cmd-1", "prompt": "Task 1"},
                {"id": "cmd-2", "prompt": "Task 2"},
            ],
            "results": []
        }
        
        memory_store.save_commands(commands_data)
        
        found = memory_store.find_command_by_id("cmd-1")
        assert found["id"] == "cmd-1"
        assert found["prompt"] == "Task 1"
        
        not_found = memory_store.find_command_by_id("cmd-999")
        assert not_found is None

