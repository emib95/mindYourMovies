from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MindYourMovies API"
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "https://mindyourmovies.com",
        "https://www.mindyourmovies.com",
    ]
    tmdb_api_key: str | None = None
    tmdb_region: str = "GB"
    tmdb_min_vote_average: float = 7.0
    tmdb_min_vote_count: int = 500
    tmdb_candidate_limit: int = 60
    geolocation_api_url: str = "https://ipwho.is/{ip}?fields=success,country_code"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    llm_first_timeout_seconds: float = 60.0
    llm_first_max_batches: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
