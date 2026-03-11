import os

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration for the entire application.
    Modular sections grouped inside one file.
    """

    # -----------------------------
    # Base Config
    # -----------------------------
    model_config = SettingsConfigDict(
        env_file=".env" if os.path.exists(".env") else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -----------------------------
    # App Settings
    # -----------------------------
    environment: str = "development"  # development / staging / production
    debug: bool = True
    app_name: str = "OmniLabsGhana API"

    # -----------------------------
    # Auth / Security
    # -----------------------------
    secret_key: SecretStr = SecretStr("change-me")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # -----------------------------
    # Database (Postgres / Supabase)
    # -----------------------------
    database_url: str = ""
    supabase_url: str | None = None
    supabase_key: str | None = None

    # -----------------------------
    # Redis
    # -----------------------------
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str | None = None

    # -----------------------------
    # Google Cloud / Vertex AI
    # -----------------------------
    gcp_project_id: str | None = None
    gcp_location: str = "europe-west1"
    gcp_credentials_path: str | None = None

    # -----------------------------
    # Email / SMTP
    # -----------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None


# Instantiate once and import everywhere
settings = Settings()