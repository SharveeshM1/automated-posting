from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All credentials come from environment variables / a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bluesky_handle: str = ""
    bluesky_app_password: str = ""
    bluesky_service: str = "https://bsky.social"

    mastodon_instance: str = ""
    mastodon_access_token: str = ""

    devto_api_key: str = ""

    github_token: str = ""
    gitlab_token: str = ""

    request_timeout_seconds: float = 15.0
    platform_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
