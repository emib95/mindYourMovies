from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Provider(str, Enum):
    netflix = "netflix"
    disney = "disney"
    prime = "prime"
    youtube = "youtube"
    hbo = "hbo"


class RecommendationRequest(BaseModel):
    providers: list[Provider] = Field(..., min_length=1)
    mood: str = Field(..., min_length=2, max_length=240)
    region: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Za-z]{2}$",
        description="ISO 3166-1 alpha-2 country code used for TMDb watch availability.",
    )
    language: Literal["en", "es"] = Field(
        default="en",
        description="UI and recommendation language.",
    )
    allow_extra_costs: bool = Field(
        default=False,
        description="Whether paid rentals or purchases outside subscriptions are acceptable.",
    )
    group_context: str | None = Field(
        default=None,
        max_length=240,
        description="Who is watching or what the group is optimizing for.",
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional extra preferences, constraints, or comments.",
    )
    excluded_tmdb_ids: list[int] = Field(
        default_factory=list,
        max_length=25,
        description="TMDb movie IDs that should not be recommended again.",
    )
    excluded_movie_titles: list[str] = Field(
        default_factory=list,
        max_length=25,
        description="Movie titles that should not be recommended again.",
    )

    @field_validator("region", mode="before")
    @classmethod
    def normalize_region(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().upper()
        return normalized or None

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: str | None) -> str:
        if value is None:
            return "en"
        return str(value).strip().lower().split("-")[0] or "en"

    @field_validator("excluded_tmdb_ids", mode="before")
    @classmethod
    def normalize_excluded_tmdb_ids(cls, value: object) -> list[int]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []

        normalized: list[int] = []
        for item in value:
            try:
                tmdb_id = int(item)
            except (TypeError, ValueError):
                continue
            if tmdb_id > 0 and tmdb_id not in normalized:
                normalized.append(tmdb_id)
        return normalized

    @field_validator("excluded_movie_titles", mode="before")
    @classmethod
    def normalize_excluded_movie_titles(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []

        normalized: list[str] = []
        for item in value:
            title = str(item).strip()
            if title and title not in normalized:
                normalized.append(title)
        return normalized


class RecommendationSearchPlan(BaseModel):
    exact_title_queries: list[str] = Field(default_factory=list, max_length=5)
    similar_to_titles: list[str] = Field(default_factory=list, max_length=5)
    search_queries: list[str] = Field(default_factory=list, max_length=6)
    genres: list[str] = Field(default_factory=list, max_length=6)
    excluded_genres: list[str] = Field(default_factory=list, max_length=6)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=10)
    tones: list[str] = Field(default_factory=list, max_length=8)
    themes: list[str] = Field(default_factory=list, max_length=8)
    release_year_min: int | None = Field(default=None, ge=1878, le=2100)
    release_year_max: int | None = Field(default=None, ge=1878, le=2100)
    runtime_max_minutes: int | None = Field(default=None, ge=30, le=360)
    original_language: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[a-z]{2}$",
    )
    strictness: Literal["low", "medium", "high"] = "medium"
    relax_quality: bool = False
    rationale: str = Field(default="", max_length=500)

    @field_validator(
        "exact_title_queries",
        "similar_to_titles",
        "search_queries",
        "genres",
        "excluded_genres",
        "keywords",
        "excluded_keywords",
        "tones",
        "themes",
        mode="before",
    )
    @classmethod
    def normalize_string_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []

        normalized: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    @field_validator("original_language", mode="before")
    @classmethod
    def normalize_original_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return normalized or None


class MovieCandidate(BaseModel):
    tmdb_id: int
    title: str
    overview: str
    release_year: str | None = None
    rating: float | None = None
    vote_count: int | None = None
    popularity: float | None = None
    provider_names: list[str]
    watch_link: HttpUrl


class RecommendationResponse(BaseModel):
    movie_title: str
    provider: str
    watch_link: HttpUrl
    reason: str
    why_recommended: str
    tmdb_id: int | None = None
    region: str
    language: Literal["en", "es"]


class LocationResponse(BaseModel):
    region: str
    source: Literal["header", "ip", "default"]
    detected: bool
