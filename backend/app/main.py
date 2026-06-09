from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from httpx import HTTPError

from app.config import get_settings
from app.schemas import LocationResponse, RecommendationRequest, RecommendationResponse
from app.services.llm import RecommendationEngine
from app.services.location import LocationResolver
from app.services.provider_links import ProviderLinkResolver
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
location_resolver = LocationResolver(settings)
provider_link_resolver = ProviderLinkResolver(settings)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "health": "/health",
        "location": "GET /api/location",
        "recommendations": "POST /api/recommendations",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/location", response_model=LocationResponse)
async def locate_user(request: Request) -> LocationResponse:
    return await location_resolver.resolve(
        request.headers,
        request.client.host if request.client else None,
    )


@app.post("/api/recommendations", response_model=RecommendationResponse)
async def create_recommendation(
    request: Request,
    recommendation_request: RecommendationRequest,
) -> RecommendationResponse:
    if recommendation_request.region is None:
        location = await location_resolver.resolve(
            request.headers,
            request.client.host if request.client else None,
        )
        recommendation_request = recommendation_request.model_copy(
            update={"region": location.region}
        )

    try:
        candidates = await tmdb_client.discover_movies(recommendation_request)
    except HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not fetch movie availability from TMDb.",
        ) from exc

    if not candidates:
        detail = _no_movies_detail(recommendation_request)
        if not recommendation_request.allow_extra_costs:
            detail = _no_included_movies_detail(recommendation_request)
        raise HTTPException(
            status_code=404,
            detail=detail,
        )

    try:
        recommendation = await recommendation_engine.recommend(
            recommendation_request,
            candidates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await provider_link_resolver.resolve(recommendation)


def _no_movies_detail(recommendation_request: RecommendationRequest) -> str:
    region = recommendation_request.region or settings.tmdb_region.upper()
    if recommendation_request.language == "es":
        return (
            "No se encontraron peliculas que cumplan los filtros de disponibilidad "
            f"y calidad para esas plataformas en {region}."
        )
    return (
        "No movies matching the availability and quality filters were found for "
        f"the selected providers in {region}."
    )


def _no_included_movies_detail(recommendation_request: RecommendationRequest) -> str:
    region = recommendation_request.region or settings.tmdb_region.upper()
    if recommendation_request.language == "es":
        return (
            "No se encontraron peliculas incluidas, gratis o con anuncios que "
            "cumplan los filtros de calidad para "
            f"esas plataformas en {region}. Prueba permitiendo alquileres o compras."
        )
    return (
        "No included, free, or ad-supported movies matching the quality filters "
        f"were found for the selected providers in {region}. Try allowing paid "
        "rentals or purchases."
    )
