import json
from pathlib import Path
from typing import Dict, Optional

import requests

CONFIG_DIR = Path(__file__).parent


def load_cursor_config() -> Dict[str, Optional[str]]:
    """
    Загружает cursor_base_url, cursor_api_key, cursor_repository
    из config.json.
    """
    config_path = CONFIG_DIR / "config.json"
    if not config_path.exists():
        config_path = CONFIG_DIR / "config.example.json"
    
    if not config_path.exists():
        raise FileNotFoundError("Neither config.json nor config.example.json found")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    return {
        "cursor_base_url": config.get("cursor_base_url", "https://api.cursor.com"),
        "cursor_api_key": config.get("cursor_api_key"),
        "cursor_repository": config.get("cursor_repository")
    }


def send_prompt_to_cursor(prompt: str) -> dict:
    """
    Отправляет запрос Cloud Agents API:
    
    POST {cursor_base_url}/v0/agents
    Authorization: Bearer <cursor_api_key>
    
    Body:
    {
      "prompt": {
        "text": "<наш prompt>"
      },
      "source": {
        "repository": "<значение из cursor_repository>"
      }
    }
    
    Возвращает JSON-ответ Cursor API как dict.
    """
    config = load_cursor_config()
    
    base_url = config["cursor_base_url"]
    api_key = config["cursor_api_key"]
    repository = config["cursor_repository"]
    
    if not api_key:
        raise ValueError("cursor_api_key not configured")
    
    url = f"{base_url}/v0/agents"
    
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "prompt": {
            "text": prompt
        }
    }
    
    if repository:
        data["source"] = {
            "repository": repository
        }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        error_text = f"HTTP {response.status_code}: {response.text}"
        raise RuntimeError(error_text) from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Request failed: {str(e)}") from e

