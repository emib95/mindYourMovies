import json
from contextlib import nullcontext
from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse

from openai import AsyncOpenAI, OpenAIError

from app.config import Settings
from app.recommendation_trace import get_trace
from app.schemas import MovieCandidate, RecommendationRequest, RecommendationResponse


LANGUAGE_LABELS = {
    "en": "English",
    "es": "Spanish",
}

FALLBACK_REASONS = {
    "en": "Picked from candidates available in {region} using your provider and mood answers.",
    "es": "Elegida entre opciones disponibles en {region} usando tus plataformas y preferencias.",
}

FALLBACK_WHY_RECOMMENDED = {
    "en": (
        "It is available in {region} from your selected providers and scored best "
        "against the mood, group, and notes you shared."
    ),
    "es": (
        "Está disponible en {region} en las plataformas seleccionadas y fue la "
        "mejor coincidencia con el ambiente, el grupo y las notas que compartiste."
    ),
}
CLASSIC_INTENT_TERMS = (
    "classic",
    "classics",
    "cinema classic",
    "movie classic",
    "film classic",
    "masterpiece",
    "masterpieces",
    "old hollywood",
    "golden age",
    "timeless",
    "canonical",
    "canon",
    "acclaimed",
    "obra maestra",
    "clásico",
    "clásicos",
    "cine clásico",
    "película clásica",
    "clasico",
    "clasicos",
    "cine clasico",
    "pelicula clasica",
)
STREAMING_PROVIDER_DOMAINS = (
    "netflix.com",
    "disneyplus.com",
    "primevideo.com",
    "amazon.com",
    "youtube.com",
    "youtu.be",
    "max.com",
    "hbomax.com",
    "nowtv.com",
)
NON_PROVIDER_DOMAINS = (
    "themoviedb.org",
    "tmdb.org",
    "justwatch.com",
    "reelgood.com",
    "imdb.com",
    "rottentomatoes.com",
    "google.com",
    "bing.com",
)

RECOMMENDATION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "movie_title": {"type": "string"},
        "provider": {"type": "string"},
        "watch_link": {"type": "string"},
        "reason": {"type": "string"},
        "why_recommended": {"type": "string"},
    },
    "required": [
        "movie_title",
        "provider",
        "watch_link",
        "reason",
        "why_recommended",
    ],
}

RECOMMENDATION_SUGGESTION_SCHEMA = RECOMMENDATION_RESPONSE_SCHEMA

WATCH_LINK_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "watch_link": {"type": "string"},
    },
    "required": ["watch_link"],
}


@dataclass(frozen=True)
class LLMRecommendationSuggestion:
    movie_title: str
    provider: str
    watch_link: str
    reason: str
    why_recommended: str


class RecommendationEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def suggest_movies(
        self,
        recommendation_request: RecommendationRequest,
        excluded_titles: set[str],
        batch_index: int = 1,
    ) -> list[LLMRecommendationSuggestion]:
        if not self.settings.openai_api_key:
            return []

        trace = get_trace()
        stage = (
            trace.stage(
                "openai_suggest_movies",
                batch=batch_index,
                model=self.settings.openai_model,
                region=self._region(recommendation_request),
            )
            if trace
            else nullcontext({})
        )

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        try:
            with stage as details:
                response = await client.responses.create(
                    model=self.settings.openai_model,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "You recommend movies for a user who wants one thing to "
                                "watch now. Use web search to identify exactly one movie "
                                "that matches the user's request and is available in the "
                                "requested country on one of the selected streaming "
                                "providers. Interpret niche requests semantically, including "
                                "directors, national cinemas, auteurs, eras, languages, "
                                "and specific styles. For example, a Sorrentino request "
                                "means films by or closely connected to Paolo Sorrentino, "
                                "and an Italian movie request should prioritize Italian "
                                "films rather than only mainstream English-language films. "
                                "Respect the user's extra-cost preference: when false, avoid "
                                "titles that are only rent or buy. Do not include excluded "
                                "titles. Prefer official provider title URLs for watch_link "
                                "when you can verify them; use an empty string if you "
                                "cannot find one. Return JSON only."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "region": self._region(recommendation_request),
                                    "language": recommendation_request.language,
                                    "selected_providers": [
                                        provider.value
                                        for provider in recommendation_request.providers
                                    ],
                                    "allow_extra_costs": (
                                        recommendation_request.allow_extra_costs
                                    ),
                                    "user_answers": recommendation_request.model_dump(
                                        mode="json"
                                    ),
                                    "excluded_titles": sorted(excluded_titles),
                                    "response_language": LANGUAGE_LABELS[
                                        recommendation_request.language
                                    ],
                                }
                            ),
                        },
                    ],
                    tools=[
                        {
                            "type": "web_search",
                            "search_context_size": "medium",
                            "user_location": {
                                "type": "approximate",
                                "country": self._region(recommendation_request),
                            },
                        }
                    ],
                    tool_choice="required",
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "movie_recommendation_suggestion",
                            "schema": RECOMMENDATION_SUGGESTION_SCHEMA,
                            "strict": True,
                        }
                    },
                )
                details["openai_response_received"] = True
        except OpenAIError as exc:
            if trace is not None:
                trace.event(
                    "openai_suggest_movies",
                    "failed",
                    batch=batch_index,
                    reason="openai_error",
                    error=str(exc),
                )
            return []

        content = self._response_text(response)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            if trace is not None:
                trace.event(
                    "openai_suggest_movies",
                    "failed",
                    batch=batch_index,
                    reason="invalid_json",
                    error=str(exc),
                    raw_content_preview=content[:200],
                )
            return []

        if not isinstance(payload, dict):
            return []

        title = self._clean_text(payload.get("movie_title"))
        if not title:
            return []

        result = [
            LLMRecommendationSuggestion(
                movie_title=title,
                provider=self._clean_text(payload.get("provider")),
                watch_link=self._clean_text(payload.get("watch_link")),
                reason=self._clean_text(payload.get("reason")),
                why_recommended=self._clean_text(payload.get("why_recommended")),
            )
        ]
        if trace is not None:
            trace.event(
                "openai_suggest_movies_parsed",
                "ok" if result else "failed",
                batch=batch_index,
                suggestion_count=len(result),
                titles=[suggestion.movie_title for suggestion in result],
            )
        return result

    async def recommend(
        self,
        recommendation_request: RecommendationRequest,
        candidates: list[MovieCandidate],
    ) -> RecommendationResponse:
        if not candidates:
            raise ValueError("At least one movie candidate is required.")

        if not self.settings.openai_api_key:
            if get_trace() is not None:
                get_trace().event(
                    "openai_recommend",
                    "skipped",
                    reason="missing_openai_api_key",
                    candidate_count=len(candidates),
                )
            return self._fallback_recommendation(recommendation_request, candidates)

        trace = get_trace()
        stage = (
            trace.stage(
                "openai_recommend",
                model=self.settings.openai_model,
                candidate_count=len(candidates),
                region=self._region(recommendation_request),
            )
            if trace
            else nullcontext({})
        )

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        try:
            with stage as details:
                response = await client.responses.create(
                    model=self.settings.openai_model,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "You help people stop scrolling and pick one movie. "
                                "Choose exactly one title from the candidate list. "
                                "Interpret the user's intent semantically in any language. "
                                "When the user asks for something similar, like, comparable, "
                                "parecido, similar a, algo como, del estilo de, or equivalent "
                                "wording around a named title, treat that title only as a "
                                "reference and choose a different candidate with a close tonal, "
                                "genre, era, or reputation match. Never choose the reference "
                                "title itself in that case, including spelling, casing, "
                                "punctuation, translation, or minor-misspelling variants of "
                                "that title. If the user names a specific title as the movie "
                                "they want and not merely as a similarity reference, strongly "
                                "prefer that exact title when it is in the candidate list. If "
                                "the named title is not available, choose a close match. "
                                "Favor well-rated candidates with stronger vote counts and popularity. "
                                "For classic, masterpiece, or cinema-canon requests, prioritize "
                                "older, highly rated, widely voted films over new releases. "
                                "Respect the user's allow_extra_costs preference when explaining the choice. "
                                "Use web search to find the official watch page for the chosen "
                                "movie on one of the selected providers available in the user's "
                                "region. Prefer a direct title deep link, such as a Netflix, "
                                "Disney+, Prime Video, YouTube, Max, HBO, or NOW title URL. If "
                                "a direct title page is not available, use an official provider "
                                "search page for the movie title. Do not return TMDb, JustWatch, "
                                "Reelgood, IMDb, Rotten Tomatoes, or search engine result pages "
                                "as watch_link. "
                                "Return JSON only with movie_title, provider, watch_link, reason, "
                                "and why_recommended. Use reason as a short summary. "
                                "Use why_recommended to explain in one or two sentences why this "
                                "movie fits the user's mood, group context, notes, selected providers, "
                                "region, and extra-cost preference. "
                                "Write reason and why_recommended in "
                                f"{LANGUAGE_LABELS[recommendation_request.language]}. "
                                "Do not invent titles or links."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "region": self._region(recommendation_request),
                                    "language": recommendation_request.language,
                                    "user_answers": recommendation_request.model_dump(mode="json"),
                                    "candidates": [
                                        candidate.model_dump(
                                            mode="json",
                                            exclude={"watch_link"},
                                        )
                                        for candidate in candidates
                                    ],
                                }
                            ),
                        },
                    ],
                    tools=[
                        {
                            "type": "web_search",
                            "search_context_size": "medium",
                            "user_location": {
                                "type": "approximate",
                                "country": self._region(recommendation_request),
                            },
                        }
                    ],
                    tool_choice="required",
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "movie_recommendation",
                            "schema": RECOMMENDATION_RESPONSE_SCHEMA,
                            "strict": True,
                        }
                    },
                )
                details["openai_response_received"] = True
        except OpenAIError as exc:
            if trace is not None:
                trace.event(
                    "openai_recommend",
                    "failed",
                    reason="openai_error",
                    error=str(exc),
                )
            return self._fallback_recommendation(recommendation_request, candidates)

        content = self._response_text(response)
        try:
            llm_payload = json.loads(content)
        except json.JSONDecodeError as exc:
            if trace is not None:
                trace.event(
                    "openai_recommend",
                    "failed",
                    reason="invalid_json",
                    error=str(exc),
                    raw_content_preview=content[:200],
                )
            return self._fallback_recommendation(recommendation_request, candidates)

        selected = self._candidate_by_title(
            candidates,
            str(llm_payload.get("movie_title", "")),
        )
        if selected is None:
            if trace is not None:
                trace.event(
                    "openai_recommend",
                    "failed",
                    reason="selected_title_not_in_candidates",
                    returned_title=llm_payload.get("movie_title"),
                )
            return self._fallback_recommendation(recommendation_request, candidates)

        fallback_reason = FALLBACK_REASONS[recommendation_request.language].format(
            region=self._region(recommendation_request),
        )
        reason = self._clean_text(llm_payload.get("reason")) or fallback_reason
        why_recommended = (
            self._clean_text(llm_payload.get("why_recommended"))
            or reason
        )
        watch_link = self._watch_link(llm_payload.get("watch_link"), selected)
        if trace is not None:
            trace.event(
                "link_verification",
                "ok" if self._is_supported_provider_url(watch_link) else "fallback",
                movie_title=selected.title,
                source="openai_recommend_response",
                watch_link=watch_link,
                llm_watch_link=self._clean_text(llm_payload.get("watch_link")),
            )

        return RecommendationResponse(
            movie_title=selected.title,
            provider=str(llm_payload.get("provider") or ", ".join(selected.provider_names)),
            watch_link=watch_link,
            reason=reason,
            why_recommended=why_recommended,
            tmdb_id=selected.tmdb_id,
            region=self._region(recommendation_request),
            language=recommendation_request.language,
        )

    async def recommendation_from_suggestion(
        self,
        recommendation_request: RecommendationRequest,
        suggestion: LLMRecommendationSuggestion,
        selected: MovieCandidate,
    ) -> RecommendationResponse:
        fallback_reason = FALLBACK_REASONS[recommendation_request.language].format(
            region=self._region(recommendation_request),
        )
        reason = self._clean_text(suggestion.reason) or fallback_reason
        why_recommended = (
            self._clean_text(suggestion.why_recommended)
            or reason
        )
        watch_link = await self._watch_link_for_suggestion(
            recommendation_request,
            suggestion,
            selected,
        )

        return RecommendationResponse(
            movie_title=selected.title,
            provider=self._verified_provider(suggestion.provider, selected),
            watch_link=watch_link,
            reason=reason,
            why_recommended=why_recommended,
            tmdb_id=selected.tmdb_id,
            region=self._region(recommendation_request),
            language=recommendation_request.language,
        )

    def _fallback_recommendation(
        self,
        recommendation_request: RecommendationRequest,
        candidates: list[MovieCandidate],
    ) -> RecommendationResponse:
        selected = self._best_keyword_match(recommendation_request, candidates)
        region = self._region(recommendation_request)
        return RecommendationResponse(
            movie_title=selected.title,
            provider=", ".join(selected.provider_names),
            watch_link=self._provider_search_link(selected),
            reason=FALLBACK_REASONS[recommendation_request.language].format(region=region),
            why_recommended=FALLBACK_WHY_RECOMMENDED[
                recommendation_request.language
            ].format(region=region),
            tmdb_id=selected.tmdb_id,
            region=region,
            language=recommendation_request.language,
        )

    def _best_keyword_match(
        self,
        recommendation_request: RecommendationRequest,
        candidates: list[MovieCandidate],
    ) -> MovieCandidate:
        query = " ".join(
            part
            for part in [
                recommendation_request.mood,
                recommendation_request.group_context or "",
                recommendation_request.notes or "",
            ]
            if part
        ).lower()

        has_classic_intent = self._has_classic_intent(query)

        def score(candidate: MovieCandidate) -> tuple[int, int, float, int, float]:
            searchable = f"{candidate.title} {candidate.overview}".lower()
            keyword_score = sum(1 for word in query.split() if word in searchable)
            classic_score = int(
                has_classic_intent
                and candidate.release_year is not None
                and self._release_year(candidate.release_year) is not None
                and self._release_year(candidate.release_year) <= 2000
            )
            rating = candidate.rating or 0
            vote_count = candidate.vote_count or 0
            popularity = candidate.popularity or 0
            return keyword_score, classic_score, rating, vote_count, popularity

        return max(candidates, key=score)

    def _candidate_by_title(
        self,
        candidates: list[MovieCandidate],
        title: str,
    ) -> MovieCandidate | None:
        normalized_title = title.strip().lower()
        for candidate in candidates:
            if candidate.title.lower() == normalized_title:
                return candidate
        return None

    def _clean_text(self, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _watch_link(self, value: object, candidate: MovieCandidate) -> str:
        link = self._clean_text(value)
        if self._is_supported_provider_url(link):
            return link
        return self._provider_search_link(candidate)

    async def _watch_link_for_suggestion(
        self,
        recommendation_request: RecommendationRequest,
        suggestion: LLMRecommendationSuggestion,
        candidate: MovieCandidate,
    ) -> str:
        trace = get_trace()
        stage = (
            trace.stage(
                "link_verification",
                movie_title=candidate.title,
                suggested_provider=suggestion.provider,
                suggestion_watch_link=suggestion.watch_link,
            )
            if trace
            else nullcontext({})
        )

        with stage as details:
            link = self._clean_text(suggestion.watch_link)
            if self._is_supported_provider_url(link):
                details["source"] = "suggestion_link"
                details["watch_link"] = link
                details["result"] = "ok"
                return link

            details["suggestion_link_valid"] = False
            direct_link = await self._find_direct_watch_link(
                recommendation_request,
                candidate,
                suggestion.provider,
            )
            if direct_link:
                details["source"] = "openai_watch_link_lookup"
                details["watch_link"] = direct_link
                details["result"] = "ok"
                return direct_link

            fallback_link = self._provider_search_link(candidate)
            details["source"] = "provider_search_fallback"
            details["watch_link"] = fallback_link
            details["result"] = "fallback"
            return fallback_link

    async def _find_direct_watch_link(
        self,
        recommendation_request: RecommendationRequest,
        candidate: MovieCandidate,
        provider: str,
    ) -> str:
        if not self.settings.openai_api_key:
            return ""

        trace = get_trace()
        stage = (
            trace.stage(
                "openai_watch_link_lookup",
                movie_title=candidate.title,
                model=self.settings.openai_model,
                suggested_provider=provider,
            )
            if trace
            else nullcontext({})
        )

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        try:
            with stage as details:
                response = await client.responses.create(
                    model=self.settings.openai_model,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "Use web search to find the official streaming-provider "
                                "title page for this movie in the requested country. "
                                "Return an empty string if you cannot verify a direct "
                                "official provider URL. Do not return TMDb, JustWatch, "
                                "Reelgood, IMDb, Rotten Tomatoes, or search engine pages."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "movie_title": candidate.title,
                                    "tmdb_id": candidate.tmdb_id,
                                    "region": self._region(recommendation_request),
                                    "verified_providers": candidate.provider_names,
                                    "suggested_provider": provider,
                                }
                            ),
                        },
                    ],
                    tools=[
                        {
                            "type": "web_search",
                            "search_context_size": "medium",
                            "user_location": {
                                "type": "approximate",
                                "country": self._region(recommendation_request),
                            },
                        }
                    ],
                    tool_choice="required",
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "movie_watch_link",
                            "schema": WATCH_LINK_RESPONSE_SCHEMA,
                            "strict": True,
                        }
                    },
                )
                details["openai_response_received"] = True
        except OpenAIError as exc:
            if trace is not None:
                trace.event(
                    "openai_watch_link_lookup",
                    "failed",
                    movie_title=candidate.title,
                    reason="openai_error",
                    error=str(exc),
                )
            return ""

        try:
            payload = json.loads(self._response_text(response))
        except json.JSONDecodeError as exc:
            if trace is not None:
                trace.event(
                    "openai_watch_link_lookup",
                    "failed",
                    movie_title=candidate.title,
                    reason="invalid_json",
                    error=str(exc),
                )
            return ""

        link = self._clean_text(payload.get("watch_link"))
        if self._is_supported_provider_url(link):
            if trace is not None:
                trace.event(
                    "openai_watch_link_lookup",
                    "ok",
                    movie_title=candidate.title,
                    watch_link=link,
                )
            return link

        if trace is not None:
            trace.event(
                "openai_watch_link_lookup",
                "failed",
                movie_title=candidate.title,
                reason="unsupported_or_empty_link",
                returned_link=link,
            )
        return ""

    def _verified_provider(
        self,
        suggested_provider: str,
        selected: MovieCandidate,
    ) -> str:
        normalized_suggestion = suggested_provider.strip().lower()
        for provider_name in selected.provider_names:
            if provider_name.lower() == normalized_suggestion:
                return provider_name
        return ", ".join(selected.provider_names)

    def _is_supported_provider_url(self, link: str) -> bool:
        if not link:
            return False

        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False

        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        if any(host == domain or host.endswith(f".{domain}") for domain in NON_PROVIDER_DOMAINS):
            return False

        return any(
            host == domain or host.endswith(f".{domain}")
            for domain in STREAMING_PROVIDER_DOMAINS
        )

    def _provider_search_link(self, candidate: MovieCandidate) -> str:
        provider_names = " ".join(candidate.provider_names).lower()
        query = quote_plus(candidate.title)

        if "netflix" in provider_names:
            return f"https://www.netflix.com/search?q={query}"
        if "disney" in provider_names:
            return f"https://www.disneyplus.com/search?q={query}"
        if "prime" in provider_names or "amazon" in provider_names:
            return f"https://www.primevideo.com/search/ref=atv_nb_sr?phrase={query}"
        if "youtube" in provider_names:
            return f"https://www.youtube.com/results?search_query={query}"
        if "hbo" in provider_names or "now" in provider_names or "max" in provider_names:
            return f"https://www.nowtv.com/search?q={query}"

        return f"https://www.google.com/search?q={query}+streaming"

    def _response_text(self, response: object) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text)

        output = getattr(response, "output", [])
        for item in output:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []):
                if getattr(content, "type", None) == "output_text":
                    return str(getattr(content, "text", ""))
        return "{}"

    def _region(self, recommendation_request: RecommendationRequest) -> str:
        return recommendation_request.region or self.settings.tmdb_region.upper()

    def _has_classic_intent(self, query: str) -> bool:
        return any(term in query for term in CLASSIC_INTENT_TERMS)

    def _release_year(self, release_year: str) -> int | None:
        try:
            return int(release_year)
        except ValueError:
            return None
