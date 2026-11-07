from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://anylo_app:dev@localhost:5432/anylo"
    database_url_owner: str = "postgresql+psycopg://anylo_owner:dev@localhost:5432/anylo"

    jwt_secret: str = Field(default="dev-only-change-me", min_length=16)
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    public_web_url: str = "http://localhost:5173"
    public_api_url: str = "http://localhost:8000"
    cors_origins: list[str] = ["http://localhost:5173"]

    media_root: str = "./media"
    media_signing_secret: str = "dev-only-media-secret"  # noqa: S105 - dev default, real value from env

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_plan_id: str = ""

    openai_api_key: str = ""
    openai_model: str = ""
    openai_model_deep: str = ""
    ai_monthly_quota_per_shop: int = 300

    whatsapp_enabled: bool = False
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""

    trial_days: int = 30
    grace_days: int = 7

    platform_gstin: str = ""
    platform_legal_name: str = "Dofida Private Limited"
    platform_state_code: str = "32"


@lru_cache
def get_settings() -> Settings:
    return Settings()
