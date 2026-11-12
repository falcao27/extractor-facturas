from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"
    llm_timeout_s: float = 60.0
    usd_to_eur: float = 0.92
    database_url: str = "postgresql+psycopg://facturas:facturas@localhost:5432/facturas"
    max_upload_mb: int = 5
    rate_limit_per_day: int = 20
    log_level: str = "INFO"


settings = Settings()
