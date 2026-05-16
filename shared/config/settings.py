import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Pydantic configuration: ignore any extra environment variables (like PORT) 
    # that are not defined as fields in this class.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # <-- This is the critical line
    )

    # App configuration
    app_name: str = "Sentinal OpsCenter V2"
    log_level: str = "info"

    # LLM (Groq)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = "llama-3.3-70b-versatile"

    # Tool Integrations (optional, defaults to empty strings)
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_repository: str = os.getenv("GITHUB_REPOSITORY", "")
    github_webhook_secret: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Observability
    omium_api_key: str = os.getenv("OMIUM_API_KEY", "")
    omium_project: str = "sentinal-opscenter-v2"

settings = Settings()
