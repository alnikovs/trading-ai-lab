import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

from orchestrator.config import (
    HyperliquidConfig,
    AlloraConfig,
    OpenAIConfig,
    BotConfig,
    CursorConfig,
    TelegramConfig,
)
from orchestrator.schemas.status import HealthResponse, ConfigSummaryResponse

APP_VERSION = "0.1.0"

router = APIRouter()

CONFIG_DIR = Path(__file__).parent.parent


def load_config_for_model() -> dict:
    """
    Загружает несекретные настройки из config.json (только для чтения model).
    Не инициализирует openai_client, только читает JSON.
    """
    config_path = CONFIG_DIR / "config.json"
    if not config_path.exists():
        config_path = CONFIG_DIR / "config.example.json"
    
    if not config_path.exists():
        raise FileNotFoundError("Neither config.json nor config.example.json found")
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    cursor_webhook_url = CursorConfig.WEBHOOK_URL
    
    return HealthResponse(
        status="ok",
        env=BotConfig.ENV,
        version=APP_VERSION,
        time_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        cursor_webhook_url=cursor_webhook_url,
    )


@router.get("/config/summary", response_model=ConfigSummaryResponse)
async def config_summary():
    """Returns configuration summary without exposing secrets."""
    try:
        config_data = load_config_for_model()
        model = config_data.get("model")
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        model = None
    
    return ConfigSummaryResponse(
        env=BotConfig.ENV,
        log_level=BotConfig.LOG_LEVEL,
        model=model,
        has_openai_key=bool(OpenAIConfig.API_KEY),
        has_hyperliquid_keys=bool(HyperliquidConfig.API_KEY and HyperliquidConfig.API_SECRET),
        has_allora_key=bool(AlloraConfig.API_KEY),
        has_cursor_key=bool(CursorConfig.API_KEY),
        has_cursor_repository=bool(CursorConfig.REPOSITORY),
        has_cursor_webhook_url=bool(CursorConfig.WEBHOOK_URL),
        has_telegram_token=bool(TelegramConfig.TOKEN),
    )

