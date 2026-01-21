from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM (OpenAI-compatible endpoint; local için: host.docker.internal)
    llm_base_url: str = "http://host.docker.internal:11434/v1"
    llm_api_key: str | None = None
    llm_model: str = "llama3.1"
    llm_timeout_seconds: int = 60
    llm_max_tool_iterations: int = 5

    # Collector
    metrics_interval_seconds: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"

    database_url_async: str
    database_url_sync: str

    log_level: str = "INFO"
    log_dir: str = "/var/log/app"
    log_full_payload: bool = True

    metrics_interval_seconds: int = 10


settings = Settings()
