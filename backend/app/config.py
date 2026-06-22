from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MindYourMovies API"
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
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
    openai_model: str = "gpt-5.4-mini"
    llm_first_timeout_seconds: float = 60.0
    llm_first_max_batches: int = 3

    # Watchmode is used purely to turn a verified TMDb movie into a regional
    # streaming deep link, replacing the web-search watch-link lookup.
    watchmode_api_key: str | None = None
    watchmode_base_url: str = "https://api.watchmode.com/v1"

    # Agentic, API-only recommendation loop. The agent drives TMDb search and
    # discovery tools, evaluates the results itself, and only finalises a movie
    # once it is a strong, available match. No web search is used on this path.
    agent_enabled: bool = True
    agent_model: str = "gpt-5.5"
    agent_timeout_seconds: float = 90.0
    agent_max_iterations: int = 14
    # Baseline quality guidance handed to the agent. It is a soft preference,
    # not a hard gate: the agent may go higher for open-ended requests and is
    # told to relax these for light, fun, or niche/theme-specific requests so
    # well-known available titles are not filtered out.
    agent_min_vote_average: float = 6.0
    agent_min_vote_count: int = 200

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
