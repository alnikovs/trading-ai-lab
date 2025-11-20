import time
import json
from typing import Dict, List

import requests

from cursor_client import send_prompt_to_cursor

ORCHESTRATOR_URL = "http://localhost:8000"
POLL_INTERVAL = 2


def get_pending_commands() -> List[Dict]:
    """Получает список pending команд от оркестратора."""
    try:
        response = requests.get(f"{ORCHESTRATOR_URL}/for-cursor/commands", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("commands", [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching commands: {e}")
        return []


def send_result(command_id: str, status: str, result: Dict) -> bool:
    """Отправляет результат выполнения команды обратно в оркестратор."""
    try:
        payload = {
            "command_id": command_id,
            "status": status,
            "result": result
        }
        response = requests.post(
            f"{ORCHESTRATOR_URL}/from-cursor/result",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending result: {e}")
        return False


def process_command(command: Dict) -> None:
    """Обрабатывает одну команду."""
    command_id = command.get("id")
    if not command_id:
        print("Command missing id, skipping")
        return
    
    command_data = command.get("command", {})
    prompt = command_data.get("prompt")
    
    if not prompt:
        print(f"Command {command_id} missing prompt, skipping")
        send_result(
            command_id,
            "error",
            {"error": "Command missing 'prompt' field"}
        )
        return
    
    try:
        print(f"Processing command {command_id}...")
        result = send_prompt_to_cursor(prompt)
        
        send_result(command_id, "ok", result)
        print(f"Command {command_id} completed successfully")
    
    except Exception as e:
        error_msg = str(e)
        print(f"Error processing command {command_id}: {error_msg}")
        send_result(
            command_id,
            "error",
            {"error": error_msg}
        )


def main():
    """Основной цикл опроса оркестратора."""
    print("Cursor runner started. Polling for commands...")
    
    while True:
        try:
            commands = get_pending_commands()
            
            if commands:
                print(f"Found {len(commands)} pending command(s)")
                for command in commands:
                    process_command(command)
            else:
                print("No pending commands")
            
            time.sleep(POLL_INTERVAL)
        
        except KeyboardInterrupt:
            print("\nStopping cursor runner...")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

