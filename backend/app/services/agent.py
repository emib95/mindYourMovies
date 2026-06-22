"""Agentic, API-only movie recommendation pipeline.

This module replaces the web-search recommendation path with a strict tool
calling agent. The LLM is given a small toolbox over the TMDb API (search,
discover, movie details, watch availability) plus a ``finalize`` tool. It plans
its own TMDb calls, evaluates the returned fields itself, and keeps searching
until it is confident a single movie is a strong, available match for the user.
Only then does it finalise, at which point we verify availability once more and
ask Watchmode for a regional streaming deep link.

The full tool-call transcript is fed back to the model on every turn, so it
remembers every movie and API response it has already seen. Every LLM turn and
every API call is logged through the recommendation tracer, including latency
and token usage.
"""

import json
from contextlib import nullcontext
from urllib.parse import quote_plus

import httpx
from openai import AsyncOpenAI, OpenAIError

from app.config import Settings
from app.recommendation_trace import get_trace
from app.services.tmdb import (
    AGENT_DISCOVER_SORT_OPTIONS,
    GENRE_NAME_TO_ID,
    TMDbClient,
)
from app.services.watchmode import WatchmodeClient
from app.schemas import (
    MovieDetails,
    RecommendationRequest,
    RecommendationResponse,
)


LANGUAGE_LABELS = {
    "en": "English",
    "es": "Spanish",
}

FALLBACK_REASON = {
    "en": "Chosen by the agent as the strongest available match for your request.",
    "es": "Elegida por el agente como la mejor coincidencia disponible para tu petición.",
}


def _agent_tools() -> list[dict]:
    sort_options = list(AGENT_DISCOVER_SORT_OPTIONS)
    genre_names = sorted({name.title() for name in GENRE_NAME_TO_ID})
    return [
        {
            "type": "function",
            "name": "search_movies",
            "description": (
                "Search TMDb for movies by title. Use this ONLY when the user "
                "names a specific film, a franchise, or a distinctive phrase. "
                "Results are NOT pre-filtered by availability, so prefer "
                "discover_movies for theme/topic requests."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "description": "Title or keywords to search."},
                    "year": {
                        "type": ["integer", "null"],
                        "description": "Optional primary release year filter.",
                    },
                    "page": {"type": ["integer", "null"], "description": "Results page (1-5)."},
                },
                "required": ["query"],
            },
        },
        {
            "type": "function",
            "name": "search_keywords",
            "description": (
                "Resolve a topic or theme phrase (e.g. 'football', 'time travel', "
                "'heist', 'based on a true story') to TMDb keyword IDs. Use this "
                "FIRST for any topic/theme/subject request, then pass the best "
                "keyword id(s) to discover_movies via its 'keywords' argument so "
                "results are pre-filtered to titles available on the user's "
                "providers. This avoids suggesting unavailable films."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Topic or theme phrase to look up, e.g. 'football'.",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "type": "function",
            "name": "discover_movies",
            "description": (
                "Discover movies on TMDb by genre, quality, era, language and "
                "runtime. This is the main tool for taste-based requests. By "
                "default results are pre-filtered to titles available on the "
                "user's selected providers in their region."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "genres": {
                        "type": ["array", "null"],
                        "items": {"type": "string", "enum": genre_names},
                        "description": "Genres the movie must include.",
                    },
                    "exclude_genres": {
                        "type": ["array", "null"],
                        "items": {"type": "string", "enum": genre_names},
                        "description": "Genres to exclude.",
                    },
                    "sort_by": {
                        "type": ["string", "null"],
                        "enum": [*sort_options, None],
                        "description": "TMDb sort order. Default popularity.desc.",
                    },
                    "min_vote_average": {
                        "type": ["number", "null"],
                        "description": "Minimum TMDb rating (0-10). Be strict.",
                    },
                    "min_vote_count": {
                        "type": ["integer", "null"],
                        "description": "Minimum number of votes. Be strict.",
                    },
                    "release_date_gte": {
                        "type": ["string", "null"],
                        "description": "Earliest release date, YYYY-MM-DD.",
                    },
                    "release_date_lte": {
                        "type": ["string", "null"],
                        "description": "Latest release date, YYYY-MM-DD.",
                    },
                    "original_language": {
                        "type": ["string", "null"],
                        "description": (
                            "ISO 639-1 language code, e.g. 'it' for Italian-"
                            "language films. Filters by SPOKEN LANGUAGE, not "
                            "country. Do NOT use this for a country/region of "
                            "origin (e.g. African, Korean, Nigerian cinema) — "
                            "use origin_country for that, since those films are "
                            "made in many languages."
                        ),
                    },
                    "origin_country": {
                        "type": ["string", "null"],
                        "description": (
                            "ISO 3166-1 country code, e.g. 'NG' Nigeria, 'ZA' "
                            "South Africa, 'KR' South Korea, 'FR' France. Filters "
                            "by the movie's country of origin. Use this for "
                            "requests about films from a country or region."
                        ),
                    },
                    "keywords": {
                        "type": ["array", "null"],
                        "items": {"type": "integer"},
                        "description": (
                            "TMDb keyword IDs the movie must match, from "
                            "search_keywords. Use this for topic/theme/subject "
                            "requests (e.g. football, heists, time travel) so "
                            "results stay pre-filtered to available titles."
                        ),
                    },
                    "runtime_gte": {"type": ["integer", "null"], "description": "Min runtime (mins)."},
                    "runtime_lte": {"type": ["integer", "null"], "description": "Max runtime (mins)."},
                    "page": {"type": ["integer", "null"], "description": "Results page (1-10)."},
                },
                "required": [],
            },
        },
        {
            "type": "function",
            "name": "movie_details",
            "description": (
                "Fetch full TMDb details for one movie: overview, tagline, "
                "runtime, genres, original language, cast, director and "
                "keywords. Use this to judge whether a candidate truly fits "
                "before finalising."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tmdb_id": {"type": "integer", "description": "TMDb movie id."},
                },
                "required": ["tmdb_id"],
            },
        },
        {
            "type": "function",
            "name": "check_availability",
            "description": (
                "Confirm a movie is available on the user's selected providers "
                "in their region under their cost preference. Always confirm "
                "availability before finalising."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tmdb_id": {"type": "integer", "description": "TMDb movie id."},
                },
                "required": ["tmdb_id"],
            },
        },
        {
            "type": "function",
            "name": "finalize_recommendation",
            "description": (
                "Lock in the single best movie. Only call this once you are "
                "confident it is a great fit for every signal the user gave and "
                "you have confirmed availability. If it is not available this "
                "call will fail and you must keep searching."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tmdb_id": {"type": "integer", "description": "TMDb movie id."},
                    "reason": {
                        "type": "string",
                        "description": "Short one-line summary of the pick.",
                    },
                    "why_recommended": {
                        "type": "string",
                        "description": (
                            "One or two sentences explaining why this movie fits "
                            "the user's mood, group, notes and constraints."
                        ),
                    },
                },
                "required": ["tmdb_id", "reason", "why_recommended"],
            },
        },
    ]


class MovieRecommendationAgent:
    def __init__(
        self,
        settings: Settings,
        tmdb_client: TMDbClient,
        watchmode_client: WatchmodeClient,
    ) -> None:
        self.settings = settings
        self.tmdb = tmdb_client
        self.watchmode = watchmode_client

    async def recommend(
        self,
        recommendation_request: RecommendationRequest,
    ) -> RecommendationResponse | None:
        if not self.settings.openai_api_key:
            return None

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        async with httpx.AsyncClient(timeout=12) as http_client:
            return await self._run_loop(
                recommendation_request,
                client,
                http_client,
            )

    async def _run_loop(
        self,
        recommendation_request: RecommendationRequest,
        client: AsyncOpenAI,
        http_client: httpx.AsyncClient,
    ) -> RecommendationResponse | None:
        trace = get_trace()
        tools = _agent_tools()
        input_items: list[object] = [
            {"role": "system", "content": self._system_prompt(recommendation_request)},
            {"role": "user", "content": json.dumps(self._user_payload(recommendation_request))},
        ]
        details_cache: dict[int, dict] = {}
        nudges = 0

        for iteration in range(1, self.settings.agent_max_iterations + 1):
            response = await self._call_model(
                client,
                input_items,
                tools,
                iteration,
            )
            if response is None:
                return None

            function_calls = [
                item
                for item in (getattr(response, "output", None) or [])
                if getattr(item, "type", None) == "function_call"
            ]

            # Echo the model's own output back so it keeps full memory of the
            # conversation and tool transcript on the next turn.
            input_items.extend(getattr(response, "output", None) or [])

            if not function_calls:
                nudges += 1
                if nudges > 2:
                    if trace is not None:
                        trace.event(
                            "agent_loop",
                            "failed",
                            reason="model_stopped_without_finalizing",
                            iteration=iteration,
                        )
                    return None
                input_items.append(
                    {
                        "role": "user",
                        "content": (
                            "Keep going. Use the TMDb tools to find a great fit and "
                            "call finalize_recommendation once you are confident. Do "
                            "not answer in plain text."
                        ),
                    }
                )
                continue

            if trace is not None:
                trace.record_tool_calls(len(function_calls))

            for call in function_calls:
                output, final = await self._execute_tool(
                    call,
                    recommendation_request,
                    http_client,
                    details_cache,
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": getattr(call, "call_id", None),
                        "output": output,
                    }
                )
                if final is not None:
                    if trace is not None:
                        trace.event(
                            "agent_loop",
                            "ok",
                            iteration=iteration,
                            movie_title=final.movie_title,
                            tmdb_id=final.tmdb_id,
                        )
                    return final

        if trace is not None:
            trace.event(
                "agent_loop",
                "failed",
                reason="max_iterations_reached",
                max_iterations=self.settings.agent_max_iterations,
            )
        return None

    async def _call_model(
        self,
        client: AsyncOpenAI,
        input_items: list[object],
        tools: list[dict],
        iteration: int,
    ) -> object | None:
        trace = get_trace()
        stage = (
            trace.stage(
                "agent_llm_turn",
                iteration=iteration,
                model=self.settings.agent_model,
            )
            if trace
            else nullcontext({})
        )
        try:
            with stage as details:
                response = await client.responses.create(
                    model=self.settings.agent_model,
                    input=input_items,
                    tools=tools,
                    tool_choice="auto",
                    parallel_tool_calls=False,
                )
                input_tokens, output_tokens = self._usage_tokens(response)
                if trace is not None:
                    trace.record_llm_usage(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                requested = [
                    getattr(item, "name", None)
                    for item in (getattr(response, "output", None) or [])
                    if getattr(item, "type", None) == "function_call"
                ]
                details["input_tokens"] = input_tokens
                details["output_tokens"] = output_tokens
                details["tool_calls_requested"] = requested
                return response
        except OpenAIError as exc:
            if trace is not None:
                trace.event(
                    "agent_llm_turn",
                    "failed",
                    iteration=iteration,
                    reason="openai_error",
                    error=str(exc),
                )
            return None

    async def _execute_tool(
        self,
        call: object,
        recommendation_request: RecommendationRequest,
        http_client: httpx.AsyncClient,
        details_cache: dict[int, dict],
    ) -> tuple[str, RecommendationResponse | None]:
        name = getattr(call, "name", "") or ""
        try:
            arguments = json.loads(getattr(call, "arguments", "") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}

        try:
            if name == "search_movies":
                result = await self.tmdb.agent_search_movies(
                    http_client,
                    recommendation_request,
                    query=str(arguments.get("query", "")).strip(),
                    year=arguments.get("year"),
                    page=arguments.get("page") or 1,
                )
                return json.dumps(result), None

            if name == "search_keywords":
                result = await self.tmdb.agent_search_keywords(
                    http_client,
                    recommendation_request,
                    query=str(arguments.get("query", "")).strip(),
                )
                return json.dumps(result), None

            if name == "discover_movies":
                result = await self.tmdb.agent_discover_movies(
                    http_client,
                    recommendation_request,
                    genres=arguments.get("genres"),
                    exclude_genres=arguments.get("exclude_genres"),
                    sort_by=arguments.get("sort_by") or "popularity.desc",
                    min_vote_average=arguments.get("min_vote_average"),
                    min_vote_count=arguments.get("min_vote_count"),
                    release_date_gte=arguments.get("release_date_gte"),
                    release_date_lte=arguments.get("release_date_lte"),
                    original_language=arguments.get("original_language"),
                    origin_country=arguments.get("origin_country"),
                    keywords=arguments.get("keywords"),
                    runtime_gte=arguments.get("runtime_gte"),
                    runtime_lte=arguments.get("runtime_lte"),
                    page=arguments.get("page") or 1,
                )
                return json.dumps(result), None

            if name == "movie_details":
                tmdb_id = int(arguments.get("tmdb_id"))
                result = await self.tmdb.agent_movie_details(
                    http_client,
                    recommendation_request,
                    tmdb_id,
                )
                details_cache[tmdb_id] = result
                return json.dumps(result), None

            if name == "check_availability":
                result = await self.tmdb.agent_watch_availability(
                    http_client,
                    recommendation_request,
                    int(arguments.get("tmdb_id")),
                )
                return json.dumps(result), None

            if name == "finalize_recommendation":
                return await self._finalize(
                    arguments,
                    recommendation_request,
                    http_client,
                    details_cache,
                )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"}), None

        return json.dumps({"error": f"unknown_tool:{name}"}), None

    async def _finalize(
        self,
        arguments: dict,
        recommendation_request: RecommendationRequest,
        http_client: httpx.AsyncClient,
        details_cache: dict[int, dict],
    ) -> tuple[str, RecommendationResponse | None]:
        tmdb_id = int(arguments.get("tmdb_id"))
        trace = get_trace()

        if self._is_excluded(tmdb_id, recommendation_request, details_cache):
            return (
                json.dumps(
                    {
                        "finalized": False,
                        "reason": "excluded_movie",
                        "message": "That movie is excluded. Pick a different one.",
                    }
                ),
                None,
            )

        availability = await self.tmdb.agent_watch_availability(
            http_client,
            recommendation_request,
            tmdb_id,
        )
        if not availability.get("available_on_selected_providers"):
            return (
                json.dumps(
                    {
                        "finalized": False,
                        "reason": "not_available",
                        "message": (
                            "Not available on the selected providers in this region. "
                            "Keep searching for an available movie."
                        ),
                    }
                ),
                None,
            )

        details = details_cache.get(tmdb_id)
        if details is None:
            details = await self.tmdb.agent_movie_details(
                http_client,
                recommendation_request,
                tmdb_id,
            )
            details_cache[tmdb_id] = details

        provider_names = [str(name) for name in availability.get("providers", [])]
        region = recommendation_request.region or self.settings.tmdb_region.upper()
        watch_link, link_source = await self._watch_link(
            http_client,
            recommendation_request,
            tmdb_id,
            details,
            provider_names,
            region,
        )

        language = recommendation_request.language
        reason = str(arguments.get("reason") or "").strip() or FALLBACK_REASON[language]
        why_recommended = (
            str(arguments.get("why_recommended") or "").strip() or reason
        )

        response = RecommendationResponse(
            movie_title=str(details.get("title") or "Unknown title"),
            provider=", ".join(provider_names) or "Selected provider",
            watch_link=watch_link,
            reason=reason,
            why_recommended=why_recommended,
            tmdb_id=tmdb_id,
            region=region,
            language=language,
            movie_details=self._movie_details_from_tmdb(details),
        )

        if trace is not None:
            trace.event(
                "agent_finalize",
                "ok",
                movie_title=response.movie_title,
                tmdb_id=tmdb_id,
                providers=provider_names,
                watch_link=watch_link,
                watch_link_source=link_source,
            )
        return json.dumps({"finalized": True, "movie_title": response.movie_title}), response

    async def _watch_link(
        self,
        http_client: httpx.AsyncClient,
        recommendation_request: RecommendationRequest,
        tmdb_id: int,
        details: dict,
        provider_names: list[str],
        region: str,
    ) -> tuple[str, str]:
        deeplink = await self.watchmode.deeplink_for_tmdb_id(
            http_client,
            tmdb_id,
            region,
            provider_names,
            recommendation_request.allow_extra_costs,
        )
        if deeplink is not None:
            return deeplink.web_url, "watchmode"

        title = str(details.get("title") or "")
        return self._provider_search_link(title, provider_names), "provider_search"

    def _provider_search_link(self, title: str, provider_names: list[str]) -> str:
        names = " ".join(provider_names).lower()
        query = quote_plus(title)
        if "netflix" in names:
            return f"https://www.netflix.com/search?q={query}"
        if "disney" in names:
            return f"https://www.disneyplus.com/search?q={query}"
        if "prime" in names or "amazon" in names:
            return f"https://www.primevideo.com/search/ref=atv_nb_sr?phrase={query}"
        if "youtube" in names:
            return f"https://www.youtube.com/results?search_query={query}"
        if "hbo" in names or "now" in names or "max" in names:
            return f"https://www.nowtv.com/search?q={query}"
        return f"https://www.google.com/search?q={query}+streaming"

    def _movie_details_from_tmdb(self, details: dict) -> MovieDetails | None:
        intro = (details.get("overview") or "").strip() or None
        actors = [str(name) for name in (details.get("cast") or [])][:8]
        if not intro and not actors:
            return None
        return MovieDetails(intro=intro, actors=actors)

    def _is_excluded(
        self,
        tmdb_id: int,
        recommendation_request: RecommendationRequest,
        details_cache: dict[int, dict],
    ) -> bool:
        if tmdb_id in set(recommendation_request.excluded_tmdb_ids):
            return True
        excluded_titles = {
            title.strip().lower()
            for title in recommendation_request.excluded_movie_titles
            if title.strip()
        }
        details = details_cache.get(tmdb_id)
        if details and str(details.get("title", "")).strip().lower() in excluded_titles:
            return True
        return False

    def _usage_tokens(self, response: object) -> tuple[int, int]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0, 0
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        return int(input_tokens), int(output_tokens)

    def _system_prompt(self, recommendation_request: RecommendationRequest) -> str:
        language = LANGUAGE_LABELS[recommendation_request.language]
        return (
            "You are a strict, decisive movie-picking agent. Your job is to find "
            "exactly ONE movie that is a great fit for the user and is available "
            "to stream on their selected providers, using only the TMDb tools "
            "provided. Do not rely on outside knowledge for availability, "
            "ratings, or vote counts; verify everything through the tools.\n\n"
            "Process:\n"
            "1. Read every user signal: mood, who is watching, notes, language, "
            "and any named titles or references.\n"
            "2. Plan TMDb calls. discover_movies is your primary tool because it "
            "pre-filters to titles AVAILABLE on the user's providers. For a "
            "topic, theme or subject in the notes/mood (e.g. football, heists, "
            "time travel, true stories), FIRST call search_keywords to get the "
            "keyword id, then call discover_movies with that id in 'keywords'. "
            "Use search_movies ONLY when the user names a specific title — its "
            "results are NOT availability-filtered, so do not use it to explore a "
            "theme (that is what caused dead-ends on unavailable films). Exploit "
            "discover filters (genres, keywords, origin_country, vote average, "
            "vote count, release dates, original language, runtime, sort). "
            "IMPORTANT: if mood and notes are empty or absent, the user has "
            "expressed NO preferences. Make ONE broad discover_movies call with no "
            "genre, language, era, or theme filters, then pick the strongest "
            "well-rated title from those results and finalise it. Do NOT run "
            "additional searches with invented filters; doing so wastes turns "
            "chasing preferences the user never gave.\n"
            "3. Inspect promising candidates with movie_details to judge true fit "
            "from overview, genres, cast, director, keywords and runtime.\n"
            "4. Be STRICT on quality. Never finalise a movie weaker than "
            f"{self.settings.agent_min_vote_average} TMDb rating with at least "
            f"{self.settings.agent_min_vote_count} votes, and prefer clearly "
            "higher-rated, well-voted films. If a candidate only partially fits, "
            "keep searching rather than settling.\n"
            "5. When a named title is given as the wanted movie, prefer that exact "
            "title; when it is only a similarity reference (like, similar to, in "
            "the style of), recommend a different, comparable film, never the "
            "reference itself.\n"
            "6. Confirm availability with check_availability, then call "
            "finalize_recommendation. If finalize fails because the movie is not "
            "available or is excluded, keep searching.\n\n"
            "Respect the user's cost preference and never recommend an excluded "
            f"title. Write reason and why_recommended in {language}. Be efficient: "
            "do not loop forever once you have found a strong, available match."
        )

    def _user_payload(self, recommendation_request: RecommendationRequest) -> dict[str, object]:
        region = recommendation_request.region or self.settings.tmdb_region.upper()
        return {
            "availability_region": region,
            "response_language": LANGUAGE_LABELS[recommendation_request.language],
            "selected_providers": [
                provider.value for provider in recommendation_request.providers
            ],
            "allow_extra_costs": recommendation_request.allow_extra_costs,
            "user_preferences": {
                "mood": recommendation_request.mood,
                "group_context": recommendation_request.group_context,
                "notes": recommendation_request.notes,
            },
            "excluded_tmdb_ids": recommendation_request.excluded_tmdb_ids,
            "excluded_movie_titles": recommendation_request.excluded_movie_titles,
            "strictness": {
                "min_vote_average": self.settings.agent_min_vote_average,
                "min_vote_count": self.settings.agent_min_vote_count,
            },
        }
