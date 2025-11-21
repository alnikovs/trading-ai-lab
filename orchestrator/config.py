import os
from pathlib import Path

from dotenv import load_dotenv

# Находим .env в корне проекта
BASE_DIR = Path(__file__).resolve().parent.parent  # C:\Bot\trading-ai-lab
env_path = BASE_DIR / ".env"

# Загружаем переменные окружения из .env
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"[config] WARNING: .env not found at {env_path}. Using system env only.")


class HyperliquidConfig:
    API_KEY: str = os.getenv("HYPERLIQUID_API_KEY", "")
    API_SECRET: str = os.getenv("HYPERLIQUID_API_SECRET", "")
    ACCOUNT_NAME: str | None = os.getenv("HYPERLIQUID_ACCOUNT_NAME")


class AlloraConfig:
    API_KEY: str = os.getenv("ALLORA_API_KEY", "")
    BASE_URL: str = os.getenv("ALLORA_API_BASE_URL", "https://api.allora.network")


class OpenAIConfig:
    API_KEY: str = os.getenv("OPENAI_API_KEY", "")


class BotConfig:
    ENV: str = os.getenv("BOT_ENV", "dev")
    LOG_LEVEL: str = os.getenv("BOT_LOG_LEVEL", "INFO")


class CursorConfig:
    API_KEY: str = os.getenv("CURSOR_API_KEY", "")
    BASE_URL: str = os.getenv("CURSOR_API_BASE", os.getenv("CURSOR_BASE_URL", "https://api.cursor.com"))
    REPOSITORY: str | None = os.getenv("CURSOR_REPOSITORY")
    BASE_REF: str = os.getenv("CURSOR_BASE_REF", "main")
    WEBHOOK_URL: str | None = os.getenv("CURSOR_WEBHOOK_URL")


class TelegramConfig:
    TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ALLOWED_USER_ID: str | None = os.getenv("TELEGRAM_ALLOWED_USER_ID")


class OrchestratorConfig:
    BASE_URL: str = os.getenv("ORCHESTRATOR_BASE_URL", "http://localhost:8000")
    CURSOR_API_KEY: str = os.getenv("CURSOR_API_KEY", "")


def get_key_preview(key: str, length: int = 4) -> str:
    """Безопасно возвращает первые символы ключа для отладки."""
    if not key or len(key) < length:
        return "N/A"
    return key[:length] + "..."


def validate_required():
    """Можно вызвать при старте, чтобы сразу понять, чего не хватает."""
    missing = []

    if not HyperliquidConfig.API_KEY or not HyperliquidConfig.API_SECRET:
        missing.append("Hyperliquid API_KEY/API_SECRET")

    if not AlloraConfig.API_KEY:
        missing.append("Allora API_KEY")

    if not OpenAIConfig.API_KEY:
        missing.append("OpenAI API_KEY")

    if missing:
        details = ", ".join(missing)
        raise RuntimeError(f"Missing required config values: {details}")
