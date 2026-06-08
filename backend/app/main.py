from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from httpx import HTTPError

from app.config import get_settings
from app.schemas import RecommendationRequest, RecommendationResponse
from app.services.llm import RecommendationEngine
from app.services.tmdb import TMDbClient


settings = get_settings()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tmdb_client = TMDbClient(settings)
recommendation_engine = RecommendationEngine(settings)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/recommendations", response_model=RecommendationResponse)
async def create_recommendation(
    recommendation_request: RecommendationRequest,
) -> RecommendationResponse:
    try:
        candidates = await tmdb_client.discover_movies(recommendation_request)
    except HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not fetch movie availability from TMDb.",
        ) from exc

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="No movies were found for the selected providers in the UK.",
        )

    try:
        return await recommendation_engine.recommend(recommendation_request, candidates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
