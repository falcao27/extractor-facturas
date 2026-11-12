from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"
    database_url: str = "postgresql+psycopg://facturas:facturas@localhost:5432/facturas"
    max_upload_mb: int = 5


settings = Settings()
