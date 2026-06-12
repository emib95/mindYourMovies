import asyncio
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from httpx import HTTPError

from app.config import get_settings
from app.recommendation_trace import clear_trace, get_trace, start_trace
from app.schemas import LocationResponse, RecommendationRequest, RecommendationResponse
from app.services.llm import LLMRecommendationSuggestion
from app.services.llm import RecommendationEngine
from app.services.location import LocationResolver
from app.services.tmdb import TMDbClient


settings = get_settings()

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
logging.getLogger("mindyourmovies.recommendation").setLevel(logging.INFO)

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
    trace = start_trace("recommendation_request")
    trace.event(
        "request_received",
        "ok",
        providers=[provider.value for provider in recommendation_request.providers],
        mood=recommendation_request.mood,
        region=recommendation_request.region,
        language=recommendation_request.language,
    )

    try:
        if recommendation_request.region is None:
            with trace.stage("location_resolve") as details:
                location = await location_resolver.resolve(
                    request.headers,
                    request.client.host if request.client else None,
                )
                recommendation_request = recommendation_request.model_copy(
                    update={"region": location.region}
                )
                details["region"] = location.region
                details["source"] = location.source

        llm_first_response = await _try_llm_first_recommendation(
            recommendation_request
        )
        if llm_first_response is not None:
            trace.finish(
                "ok",
                path_used="llm_first",
                movie_title=llm_first_response.movie_title,
                tmdb_id=llm_first_response.tmdb_id,
            )
            return llm_first_response

        response = await _tmdb_first_recommendation(recommendation_request)
        trace.finish(
            "ok",
            path_used="tmdb_first",
            movie_title=response.movie_title,
            tmdb_id=response.tmdb_id,
        )
        return response
    except HTTPException as exc:
        trace.finish("failed", http_status=exc.status_code, detail=str(exc.detail))
        raise
    except Exception as exc:
        trace.finish("failed", error=str(exc))
        raise
    finally:
        clear_trace()


async def _try_llm_first_recommendation(
    recommendation_request: RecommendationRequest,
) -> RecommendationResponse | None:
    trace = get_trace()
    if not settings.openai_api_key:
        if trace is not None:
            trace.event("llm_first_path", "skipped", reason="missing_openai_api_key")
        return None

    try:
        with trace.stage(
            "llm_first_path",
            timeout_seconds=settings.llm_first_timeout_seconds,
        ) if trace else _null_stage() as details:
            result = await asyncio.wait_for(
                _llm_first_recommendation(recommendation_request),
                timeout=settings.llm_first_timeout_seconds,
            )
            if trace is not None:
                details["result"] = "matched" if result is not None else "no_match"
            return result
    except asyncio.TimeoutError:
        if trace is not None:
            trace.event(
                "llm_first_path",
                "failed",
                reason="timeout",
                timeout_seconds=settings.llm_first_timeout_seconds,
            )
        return None
    except (HTTPError, ValueError) as exc:
        if trace is not None:
            trace.event("llm_first_path", "failed", reason=type(exc).__name__, error=str(exc))
        return None


async def _llm_first_recommendation(
    recommendation_request: RecommendationRequest,
) -> RecommendationResponse | None:
    trace = get_trace()
    seen_titles = set(recommendation_request.excluded_movie_titles)
    batch_count = max(1, settings.llm_first_max_batches)

    for batch_index in range(1, batch_count + 1):
        suggestions = await recommendation_engine.suggest_movies(
            recommendation_request,
            seen_titles,
            batch_index=batch_index,
        )
        if not suggestions:
            if trace is not None:
                trace.event(
                    "openai_suggest_movies",
                    "failed",
                    batch=batch_index,
                    reason="no_suggestions_returned",
                )
            return None

        for suggestion_index, suggestion in enumerate(suggestions, start=1):
            seen_titles.add(suggestion.movie_title)
            candidate = await tmdb_client.available_candidate_for_title(
                suggestion.movie_title,
                recommendation_request,
                batch_index=batch_index,
                suggestion_index=suggestion_index,
            )
            if candidate is None:
                continue
            return await recommendation_engine.recommendation_from_suggestion(
                recommendation_request,
                _suggestion_with_verified_title(suggestion, candidate.title),
                candidate,
            )

    if trace is not None:
        trace.event(
            "llm_first_verification",
            "failed",
            reason="no_verified_candidate",
            batches_attempted=batch_count,
        )
    return None


async def _tmdb_first_recommendation(
    recommendation_request: RecommendationRequest,
) -> RecommendationResponse:
    trace = get_trace()
    if trace is not None:
        trace.event("tmdb_first_path", "ok", reason="llm_first_unavailable_or_exhausted")

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
        return await recommendation_engine.recommend(
            recommendation_request,
            candidates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _null_stage():
    from contextlib import nullcontext

    return nullcontext({})


def _suggestion_with_verified_title(
    suggestion: LLMRecommendationSuggestion,
    verified_title: str,
) -> LLMRecommendationSuggestion:
    if suggestion.movie_title == verified_title:
        return suggestion
    return LLMRecommendationSuggestion(
        movie_title=verified_title,
        provider=suggestion.provider,
        watch_link=suggestion.watch_link,
        reason=suggestion.reason,
        why_recommended=suggestion.why_recommended,
        movie_details=suggestion.movie_details,
    )


def _no_movies_detail(recommendation_request: RecommendationRequest) -> str:
    region = recommendation_request.region or settings.tmdb_region.upper()
    if recommendation_request.language == "es":
        return (
            "No se encontraron películas que cumplan los filtros de disponibilidad "
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
            "No se encontraron películas incluidas, gratis o con anuncios que "
            "cumplan los filtros de calidad para "
            f"esas plataformas en {region}. Prueba permitiendo alquileres o compras."
        )
    return (
        "No included, free, or ad-supported movies matching the quality filters "
        f"were found for the selected providers in {region}. Try allowing paid "
        "rentals or purchases."
    )
