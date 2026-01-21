from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"

    database_url_async: str
    database_url_sync: str

    log_level: str = "INFO"
    log_dir: str = "/var/log/app"
    log_full_payload: bool = True

    metrics_interval_seconds: int = 10


settings = Settings()
