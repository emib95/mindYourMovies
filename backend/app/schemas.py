from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class Provider(str, Enum):
    netflix = "netflix"
    disney = "disney"
    prime = "prime"
    youtube = "youtube"
    hbo = "hbo"


class RecommendationRequest(BaseModel):
    providers: list[Provider] = Field(..., min_length=1)
    mood: str = Field(..., min_length=2, max_length=240)
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


class MovieCandidate(BaseModel):
    tmdb_id: int
    title: str
    overview: str
    release_year: str | None = None
    rating: float | None = None
    provider_names: list[str]
    watch_link: HttpUrl


class RecommendationResponse(BaseModel):
    movie_title: str
    provider: str
    watch_link: HttpUrl
    reason: str
    tmdb_id: int | None = None
