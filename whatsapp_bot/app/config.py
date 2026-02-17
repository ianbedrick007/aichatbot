import logging
import sys

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhatsAppSettings(BaseSettings):
    """WhatsApp API configuration settings"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    access_token: SecretStr
    your_phone_number: str | None = None
    app_id: str | None = None
    app_secret: SecretStr | None = None
    recipient_waid: str | None = None
    version: str = "v18.0"
    phone_number_id: str | None = None
    verify_token: SecretStr


def configure_logging():
    """Configure logging for WhatsApp bot"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )


# Global settings instance
whatsapp_settings = WhatsAppSettings()  # type: ignore[call-arg]
