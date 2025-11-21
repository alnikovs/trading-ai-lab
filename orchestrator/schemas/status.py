from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    env: str
    version: str
    time_utc: str
    cursor_webhook_url: str | None = None


class ConfigSummaryResponse(BaseModel):
    env: str
    log_level: str
    model: str | None
    has_openai_key: bool
    has_hyperliquid_keys: bool
    has_allora_key: bool
    has_cursor_key: bool = False
    has_cursor_repository: bool = False
    has_cursor_webhook_url: bool = False
    has_telegram_token: bool = False

