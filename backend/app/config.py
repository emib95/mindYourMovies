from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MindYourMovies API"
    allowed_origins: list[str] = ["http://localhost:5173"]
    tmdb_api_key: str | None = None
    tmdb_region: str = "GB"
    tmdb_min_vote_average: float = 6.5
    tmdb_min_vote_count: int = 50
    geolocation_api_url: str = "https://ipwho.is/{ip}?fields=success,country_code"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
