import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("orchestrator.memory_store")

CONFIG_DIR = Path(__file__).parent
MEMORY_DIR = Path(__file__).parent.parent / "memory"


def load_config() -> Dict:
    config_path = CONFIG_DIR / "config.json"
    if not config_path.exists():
        config_path = CONFIG_DIR / "config.example.json"
    
    if not config_path.exists():
        raise FileNotFoundError("Neither config.json nor config.example.json found")
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse config.json", extra={"path": str(config_path), "error": str(e)}, exc_info=True)
        raise
    except IOError as e:
        logger.error("Failed to read config.json", extra={"path": str(config_path), "error": str(e)}, exc_info=True)
        raise


def load_message_history(user_id: str, max_messages: int = 10) -> List[Dict[str, str]]:
    messages_file = MEMORY_DIR / f"messages_{user_id}.jsonl"
    
    if not messages_file.exists():
        return []
    
    try:
        messages = []
        with open(messages_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "Failed to parse message line",
                            extra={"user_id": user_id, "line_preview": line[:50], "error": str(e)}
                        )
                        continue
        
        return messages[-max_messages:] if len(messages) > max_messages else messages
    except IOError as e:
        logger.error(
            "Failed to read message history",
            extra={"user_id": user_id, "path": str(messages_file), "error": str(e)},
            exc_info=True
        )
        return []


def save_messages(user_id: str, user_message: str, assistant_message: str) -> None:
    messages_file = MEMORY_DIR / f"messages_{user_id}.jsonl"
    
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    except IOError as e:
        logger.error(
            "Failed to create memory directory",
            extra={"path": str(MEMORY_DIR), "error": str(e)},
            exc_info=True
        )
        raise
    
    try:
        with open(messages_file, "a", encoding="utf-8") as f:
            user_json = json.dumps({"role": "user", "content": user_message}, ensure_ascii=False)
            assistant_json = json.dumps({"role": "assistant", "content": assistant_message}, ensure_ascii=False)
            f.write(user_json + "\n")
            f.write(assistant_json + "\n")
    except (TypeError, ValueError) as e:
        logger.error(
            "Failed to serialize messages to JSON",
            extra={"user_id": user_id, "error": str(e)},
            exc_info=True
        )
        raise IOError(f"Failed to save messages: {e}")
    except IOError as e:
        logger.error(
            "Failed to write messages to file",
            extra={"user_id": user_id, "path": str(messages_file), "error": str(e)},
            exc_info=True
        )
        raise IOError(f"Failed to save messages: {e}")


def load_ai_contract() -> str:
    docs_dir = Path(__file__).parent.parent / "docs"
    contract_file = docs_dir / "ai_contract.md"
    
    if not contract_file.exists():
        return ""
    
    try:
        with open(contract_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else ""
    except IOError as e:
        logger.warning(
            "Failed to read AI contract",
            extra={"path": str(contract_file), "error": str(e)}
        )
        return ""


def load_project_summary() -> str:
    summary_file = MEMORY_DIR / "project_summary.md"
    
    if not summary_file.exists():
        return ""
    
    try:
        with open(summary_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else ""
    except IOError as e:
        logger.warning(
            "Failed to read project summary",
            extra={"path": str(summary_file), "error": str(e)}
        )
        return ""


def load_tasks() -> Dict:
    tasks_file = MEMORY_DIR / "tasks.json"
    
    if not tasks_file.exists():
        return {"tasks": []}
    
    try:
        with open(tasks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "tasks" not in data:
                logger.warning("Invalid tasks.json format", extra={"path": str(tasks_file)})
                return {"tasks": []}
            return data
    except json.JSONDecodeError as e:
        logger.error(
            "Failed to parse tasks.json",
            extra={"path": str(tasks_file), "error": str(e)},
            exc_info=True
        )
        return {"tasks": []}
    except IOError as e:
        logger.error(
            "Failed to read tasks.json",
            extra={"path": str(tasks_file), "error": str(e)},
            exc_info=True
        )
        return {"tasks": []}


def save_tasks(data: Dict) -> None:
    tasks_file = MEMORY_DIR / "tasks.json"
    
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    except IOError as e:
        logger.error(
            "Failed to create memory directory",
            extra={"path": str(MEMORY_DIR), "error": str(e)},
            exc_info=True
        )
        raise
    
    try:
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as e:
        logger.error(
            "Failed to serialize tasks to JSON",
            extra={"error": str(e)},
            exc_info=True
        )
        raise IOError(f"Failed to save tasks: {e}")
    except IOError as e:
        logger.error(
            "Failed to write tasks to file",
            extra={"path": str(tasks_file), "error": str(e)},
            exc_info=True
        )
        raise IOError(f"Failed to save tasks: {e}")


def load_recent_results(max_results: int = 10) -> List[Dict]:
    data = load_commands()
    results = data.get("results", [])
    
    return results[-max_results:] if len(results) > max_results else results


def load_commands() -> Dict:
    commands_file = MEMORY_DIR / "commands.json"
    
    if not commands_file.exists():
        return {"commands": [], "results": []}
    
    try:
        with open(commands_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("Invalid commands.json format", extra={"path": str(commands_file)})
                return {"commands": [], "results": []}
            if "commands" not in data:
                data["commands"] = []
            if "results" not in data:
                data["results"] = []
            return data
    except json.JSONDecodeError as e:
        logger.error(
            "Failed to parse commands.json",
            extra={"path": str(commands_file), "error": str(e)},
            exc_info=True
        )
        return {"commands": [], "results": []}
    except IOError as e:
        logger.error(
            "Failed to read commands.json",
            extra={"path": str(commands_file), "error": str(e)},
            exc_info=True
        )
        return {"commands": [], "results": []}


def save_commands(data: Dict) -> None:
    commands_file = MEMORY_DIR / "commands.json"
    
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    except IOError as e:
        logger.error(
            "Failed to create memory directory",
            extra={"path": str(MEMORY_DIR), "error": str(e)},
            exc_info=True
        )
        raise
    
    try:
        with open(commands_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as e:
        logger.error(
            "Failed to serialize commands to JSON",
            extra={"error": str(e)},
            exc_info=True
        )
        raise IOError(f"Failed to save commands: {e}")
    except IOError as e:
        logger.error(
            "Failed to write commands to file",
            extra={"path": str(commands_file), "error": str(e)},
            exc_info=True
        )
        raise IOError(f"Failed to save commands: {e}")


def find_command_by_id(command_id: str) -> Dict:
    data = load_commands()
    for cmd in data.get("commands", []):
        if cmd.get("id") == command_id:
            return cmd
    return None

