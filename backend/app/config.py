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
    # Single combined web search tuning. One web search now selects the movie,
    # its watch link, and its details for several ranked titles at once, so the
    # context size is raised and the batch holds enough alternatives to cover
    # the "I've already watched that" flow without another search.
    web_search_context_size: str = "high"
    recommendation_batch_size: int = 3
    # Aggressive caching of the combined web-search results. Similar future
    # searches and the "recommend a different movie" flow are served from the
    # cached batch instead of paying for another web search.
    recommendation_cache_ttl_seconds: float = 86400.0
    recommendation_cache_max_entries: int = 512
    # Watch-link validation runs before a recommendation is exposed to the
    # frontend. If a title's link is dead, the next movie in the batch is used.
    watch_link_validation_timeout_seconds: float = 5.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
