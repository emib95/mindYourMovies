import asyncio
import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx

from app.config import Settings
from app.schemas import MovieCandidate, Provider, RecommendationRequest


@dataclass(frozen=True)
class ProviderConfig:
    label: str
    tmdb_ids: tuple[int, ...]


@dataclass(frozen=True)
class ReferenceCandidateResult:
    candidates: list[MovieCandidate]
    excluded_seed_id: int | None = None


PROVIDER_CONFIG: dict[Provider, ProviderConfig] = {
    Provider.netflix: ProviderConfig("Netflix", (8,)),
    Provider.disney: ProviderConfig("Disney+", (337,)),
    Provider.prime: ProviderConfig("Prime Video", (9, 119)),
    Provider.youtube: ProviderConfig("YouTube", (192,)),
    Provider.hbo: ProviderConfig("HBO / NOW", (39, 384, 1899)),
}

INCLUDED_MONETIZATION_TYPES = ("flatrate", "free", "ads")
PAID_MONETIZATION_TYPES = ("rent", "buy")
LANGUAGE_LOCALES = {
    "en": "en-US",
    "es": "es-ES",
}

CLASSIC_RELEASE_DATE_CUTOFF = "2000-12-31"
MIN_CLASSIC_VOTE_COUNT = 1000
MAX_REFERENCE_QUERIES = 3
MAX_REFERENCE_RELATED_MOVIES = 40
MAX_AVAILABILITY_REQUESTS = 8
FUZZY_REFERENCE_TITLE_THRESHOLD = 0.82
MIN_FUZZY_REFERENCE_LENGTH = 6

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
    "auteur",
    "acclaimed",
    "obra maestra",
    "clasico",
    "clasicos",
    "cine clasico",
    "pelicula clasica",
)
GENERIC_REFERENCE_WORDS = {
    "action",
    "adventure",
    "animated",
    "animation",
    "auteur",
    "canonical",
    "children",
    "cinema",
    "classic",
    "classics",
    "comedy",
    "comedies",
    "comfort",
    "cozy",
    "dark",
    "date",
    "documentary",
    "drama",
    "dramatic",
    "easy",
    "family",
    "film",
    "friends",
    "fun",
    "funny",
    "good",
    "great",
    "happy",
    "horror",
    "kids",
    "light",
    "like",
    "masterpiece",
    "mood",
    "movie",
    "new",
    "old",
    "romance",
    "romantic",
    "sad",
    "scary",
    "similar",
    "something",
    "stunning",
    "tense",
    "thriller",
    "timeless",
    "to",
    "visual",
    "visually",
    "watch",
}
SIMILARITY_REFERENCE_PATTERNS = (
    r"\bsimilar(?:\s+(?:movie|film|movies|films|pel[ií]cula|pel[ií]culas|"
    r"peli|pelis|filme|filmes))?\s+(?:to|a|al|à|an|zu)\s+([^,.;:\n]+)",
    r"\b(?:something|anything|movie|film|movies|films|one|algo|una|uno|"
    r"pel[ií]cula|pel[ií]culas|peli|pelis|filme|filmes)\s+"
    r"(?:like|como|similar(?:es)?\s+a|parecid[oa]s?\s+a)\s+([^,.;:\n]+)",
    r"\bin the (?:same )?(?:vein|style|mood|vibe) as\s+([^,.;:\n]+)",
    r"\balong the lines of\s+([^,.;:\n]+)",
    r"\b(?:parecid[oa]s?|similar(?:es)?)\s+(?:a|al)\s+([^,.;:\n]+)",
    r"\bparecida a\s+([^,.;:\n]+)",
    r"\bparecido a\s+([^,.;:\n]+)",
    r"\b(?:del|en el|de ese|de ese mismo)\s+estilo\s+(?:de|que)\s+([^,.;:\n]+)",
    r"\b(?:misma|mismo)\s+(?:l[ií]nea|onda|vibra|estilo)\s+(?:que|de)\s+([^,.;:\n]+)",
)
REFERENCE_PATTERNS = (
    *SIMILARITY_REFERENCE_PATTERNS,
    r"\blike\s+([^,.;:\n]+)",
    r"\bin the mood for\s+([^,.;:\n]+)",
    r"\bcomo\s+([^,.;:\n]+)",
)


DEMO_CANDIDATES = [
    MovieCandidate(
        tmdb_id=550,
        title="Fight Club",
        overview="An insomniac office worker and a soap maker form an underground fight club that spirals into something much larger.",
        release_year="1999",
        rating=8.4,
        vote_count=30000,
        popularity=78.0,
        provider_names=["Netflix"],
        watch_link="https://www.themoviedb.org/movie/550/watch?locale=GB",
    ),
    MovieCandidate(
        tmdb_id=324857,
        title="Spider-Man: Into the Spider-Verse",
        overview="Teen Miles Morales becomes Spider-Man and joins heroes from across the multiverse.",
        release_year="2018",
        rating=8.4,
        vote_count=16000,
        popularity=85.0,
        provider_names=["Disney+"],
        watch_link="https://www.themoviedb.org/movie/324857/watch?locale=GB",
    ),
    MovieCandidate(
        tmdb_id=588228,
        title="The Tomorrow War",
        overview="A family man is drafted into a future war where humanity is losing against a deadly alien species.",
        release_year="2021",
        rating=7.5,
        vote_count=3500,
        popularity=45.0,
        provider_names=["Prime Video"],
        watch_link="https://www.themoviedb.org/movie/588228/watch?locale=GB",
    ),
    MovieCandidate(
        tmdb_id=157336,
        title="Interstellar",
        overview="Explorers travel through a wormhole in space in an attempt to ensure humanity's survival.",
        release_year="2014",
        rating=8.5,
        vote_count=37000,
        popularity=120.0,
        provider_names=["YouTube"],
        watch_link="https://www.themoviedb.org/movie/157336/watch?locale=GB",
    ),
]


class TMDbClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = "https://api.themoviedb.org/3"

    async def available_candidate_for_title(
        self,
        title: str,
        recommendation_request: RecommendationRequest,
    ) -> MovieCandidate | None:
        region = self._region(recommendation_request)
        if not self.settings.tmdb_api_key:
            return self._demo_candidate_for_title(title, recommendation_request, region)

        provider_ids = self._provider_ids(recommendation_request.providers)
        language = self._language(recommendation_request, region)
        excluded_ids = set(recommendation_request.excluded_tmdb_ids)
        excluded_titles = self._excluded_movie_titles(recommendation_request)

        async with httpx.AsyncClient(timeout=12) as client:
            search_payload = await self._get_json(
                client,
                "/search/movie",
                {
                    "include_adult": "false",
                    "language": language,
                    "page": 1,
                    "query": title,
                },
            )
            for movie in self._rank_reference_seeds(
                search_payload.get("results", []),
                title,
            )[:5]:
                if not self._is_plausible_title_match(movie, title):
                    continue
                movie_id = movie.get("id")
                if not movie_id:
                    continue
                provider_names = await self._available_provider_names(
                    client,
                    int(movie_id),
                    recommendation_request,
                    region,
                    provider_ids,
                )
                if not provider_names:
                    continue

                candidate = self._candidate_from_movie(movie, provider_names, region)
                if self._is_excluded_candidate(
                    candidate,
                    excluded_ids,
                    excluded_titles,
                ):
                    continue
                return candidate

        return None

    async def discover_movies(
        self, recommendation_request: RecommendationRequest
    ) -> list[MovieCandidate]:
        region = self._region(recommendation_request)
        if not self.settings.tmdb_api_key:
            return self._demo_candidates(recommendation_request, region)

        provider_ids = self._provider_ids(recommendation_request.providers)
        language = self._language(recommendation_request, region)
        candidate_limit = self._candidate_limit()
        candidates: list[MovieCandidate] = []
        similarity_reference_queries = {
            self._normalized_text(query)
            for query in self._similarity_reference_queries(recommendation_request)
        }
        excluded_reference_ids: set[int] = set()

        async with httpx.AsyncClient(timeout=12) as client:
            for query in self._reference_queries(recommendation_request)[
                :MAX_REFERENCE_QUERIES
            ]:
                reference_result = await self._reference_candidates(
                    client,
                    query,
                    recommendation_request,
                    region,
                    provider_ids,
                    language,
                    self._normalized_text(query) in similarity_reference_queries,
                )
                candidates.extend(reference_result.candidates)
                if reference_result.excluded_seed_id is not None:
                    excluded_reference_ids.add(reference_result.excluded_seed_id)

            candidates.extend(
                await self._discover_candidates(
                    client,
                    recommendation_request,
                    region,
                    provider_ids,
                    language,
                    candidate_limit,
                )
            )

        return self._rank_and_limit_candidates(
            candidates,
            recommendation_request,
            candidate_limit,
            excluded_reference_ids,
        )

    async def _reference_candidates(
        self,
        client: httpx.AsyncClient,
        query: str,
        recommendation_request: RecommendationRequest,
        region: str,
        provider_ids: Sequence[int],
        language: str,
        exclude_seed: bool,
    ) -> ReferenceCandidateResult:
        search_payload = await self._get_json(
            client,
            "/search/movie",
            {
                "include_adult": "false",
                "language": language,
                "page": 1,
                "query": query,
            },
        )
        seed = self._best_reference_seed(search_payload.get("results", []), query)
        if seed is None:
            return ReferenceCandidateResult([])

        seed_id = seed.get("id")
        if not seed_id:
            return ReferenceCandidateResult([])

        related_movies: list[dict] = [] if exclude_seed else [seed]
        for relation in ("recommendations", "similar"):
            payload = await self._get_json(
                client,
                f"/movie/{seed_id}/{relation}",
                {
                    "language": language,
                    "page": 1,
                },
            )
            related_movies.extend(payload.get("results", []))

        return ReferenceCandidateResult(
            await self._available_candidates_from_movies(
                client,
                related_movies[:MAX_REFERENCE_RELATED_MOVIES],
                recommendation_request,
                region,
                provider_ids,
            ),
            int(seed_id) if exclude_seed else None,
        )

    async def _discover_candidates(
        self,
        client: httpx.AsyncClient,
        recommendation_request: RecommendationRequest,
        region: str,
        provider_ids: Sequence[int],
        language: str,
        candidate_limit: int,
    ) -> list[MovieCandidate]:
        provider_names = self._provider_names(recommendation_request.providers)
        candidates: list[MovieCandidate] = []
        page_count = max(1, math.ceil(candidate_limit / 20))

        for params in self._discover_param_sets(
            recommendation_request,
            region,
            provider_ids,
            language,
        ):
            for page in range(1, page_count + 1):
                payload = await self._get_json(
                    client,
                    "/discover/movie",
                    {
                        **params,
                        "page": page,
                    },
                )
                candidates.extend(
                    self._candidate_from_movie(movie, provider_names, region)
                    for movie in payload.get("results", [])
                    if movie.get("id") and self._passes_quality_threshold(movie)
                )

        return candidates

    async def _available_candidates_from_movies(
        self,
        client: httpx.AsyncClient,
        movies: Sequence[dict],
        recommendation_request: RecommendationRequest,
        region: str,
        provider_ids: Sequence[int],
    ) -> list[MovieCandidate]:
        deduped_movies = list(self._dedupe_movies(movies))
        semaphore = asyncio.Semaphore(MAX_AVAILABILITY_REQUESTS)

        async def candidate_for_movie(movie: dict) -> MovieCandidate | None:
            if not movie.get("id") or not self._passes_quality_threshold(movie):
                return None
            async with semaphore:
                provider_names = await self._available_provider_names(
                    client,
                    int(movie["id"]),
                    recommendation_request,
                    region,
                    provider_ids,
                )
            if not provider_names:
                return None
            return self._candidate_from_movie(movie, provider_names, region)

        results = await asyncio.gather(
            *(candidate_for_movie(movie) for movie in deduped_movies)
        )
        return [candidate for candidate in results if candidate is not None]

    async def _available_provider_names(
        self,
        client: httpx.AsyncClient,
        tmdb_id: int,
        recommendation_request: RecommendationRequest,
        region: str,
        provider_ids: Sequence[int],
    ) -> list[str]:
        payload = await self._get_json(
            client,
            f"/movie/{tmdb_id}/watch/providers",
            {},
        )
        region_payload = payload.get("results", {}).get(region, {})
        selected_provider_ids = set(provider_ids)
        provider_names: list[str] = []

        for monetization_type in self._monetization_type_list(recommendation_request):
            for provider in region_payload.get(monetization_type, []):
                if provider.get("provider_id") in selected_provider_ids:
                    provider_names.append(
                        provider.get("provider_name")
                        or self._provider_name_by_id(provider["provider_id"])
                    )

        return list(dict.fromkeys(provider_names))

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, object],
    ) -> dict:
        response = await client.get(
            f"{self.base_url}{path}",
            params={
                "api_key": self.settings.tmdb_api_key,
                **params,
            },
        )
        response.raise_for_status()
        return response.json()

    def _discover_param_sets(
        self,
        recommendation_request: RecommendationRequest,
        region: str,
        provider_ids: Sequence[int],
        language: str,
    ) -> list[dict[str, object]]:
        base_params = {
            "include_adult": "false",
            "include_video": "false",
            "language": language,
            "vote_average.gte": self.settings.tmdb_min_vote_average,
            "vote_count.gte": self.settings.tmdb_min_vote_count,
            "watch_region": region,
            "with_watch_monetization_types": self._monetization_types(
                recommendation_request
            ),
            "with_watch_providers": "|".join(
                str(provider_id) for provider_id in provider_ids
            ),
        }

        if not self._has_classic_intent(recommendation_request):
            return [
                {
                    **base_params,
                    "sort_by": "popularity.desc",
                }
            ]

        return [
            {
                **base_params,
                "primary_release_date.lte": CLASSIC_RELEASE_DATE_CUTOFF,
                "sort_by": "vote_average.desc",
                "vote_count.gte": max(
                    int(self.settings.tmdb_min_vote_count),
                    MIN_CLASSIC_VOTE_COUNT,
                ),
            },
            {
                **base_params,
                "sort_by": "popularity.desc",
            },
        ]

    def _candidate_from_movie(
        self,
        movie: dict,
        provider_names: Sequence[str],
        region: str,
    ) -> MovieCandidate:
        return MovieCandidate(
            tmdb_id=movie["id"],
            title=movie.get("title") or movie.get("original_title") or "Unknown title",
            overview=movie.get("overview") or "No overview available.",
            release_year=(movie.get("release_date") or "")[:4] or None,
            rating=movie.get("vote_average"),
            vote_count=movie.get("vote_count"),
            popularity=movie.get("popularity"),
            provider_names=list(provider_names),
            watch_link=f"https://www.themoviedb.org/movie/{movie['id']}/watch?locale={region}",
        )

    def _rank_and_limit_candidates(
        self,
        candidates: Sequence[MovieCandidate],
        recommendation_request: RecommendationRequest,
        limit: int,
        excluded_tmdb_ids: Iterable[int] = (),
    ) -> list[MovieCandidate]:
        excluded_ids = set(excluded_tmdb_ids).union(
            recommendation_request.excluded_tmdb_ids
        )
        excluded_titles = {
            self._normalized_text(query)
            for query in self._similarity_reference_queries(recommendation_request)
        }.union(self._excluded_movie_titles(recommendation_request))
        deduped_candidates = [
            candidate
            for candidate in self._dedupe_candidates(candidates)
            if not self._is_excluded_candidate(
                candidate,
                excluded_ids,
                excluded_titles,
            )
        ]
        return sorted(
            deduped_candidates,
            key=lambda candidate: self._candidate_score(
                candidate,
                recommendation_request,
            ),
            reverse=True,
        )[:limit]

    def _candidate_score(
        self,
        candidate: MovieCandidate,
        recommendation_request: RecommendationRequest,
    ) -> tuple[int, int, int, float, int, float]:
        query = self._normalized_text(self._request_text(recommendation_request))
        title = self._normalized_text(candidate.title)
        reference_queries = [
            self._normalized_text(reference_query)
            for reference_query in self._reference_queries(recommendation_request)
        ]
        exact_reference_match = int(title in reference_queries)
        keyword_score = sum(
            1
            for word in query.split()
            if len(word) > 2
            and word not in GENERIC_REFERENCE_WORDS
            and word in self._normalized_text(f"{candidate.title} {candidate.overview}")
        )
        classic_match = int(
            self._has_classic_intent(recommendation_request)
            and self._release_year(candidate) is not None
            and self._release_year(candidate) <= 2000
        )
        rating = candidate.rating or 0
        vote_count = candidate.vote_count or 0
        popularity = candidate.popularity or 0
        return (
            exact_reference_match,
            keyword_score,
            classic_match,
            rating,
            vote_count,
            popularity,
        )

    def _demo_candidates(
        self, recommendation_request: RecommendationRequest, region: str
    ) -> list[MovieCandidate]:
        selected_labels = set(self._provider_names(recommendation_request.providers))
        eligible_candidates = [
            self._with_region(candidate, region)
            for candidate in DEMO_CANDIDATES
            if self._candidate_passes_quality_threshold(candidate)
            and not self._is_excluded_candidate(
                candidate,
                set(recommendation_request.excluded_tmdb_ids),
                self._excluded_movie_titles(recommendation_request),
            )
        ]
        matching = [
            candidate
            for candidate in eligible_candidates
            if selected_labels.intersection(candidate.provider_names)
        ]
        return matching or eligible_candidates

    def _demo_candidate_for_title(
        self,
        title: str,
        recommendation_request: RecommendationRequest,
        region: str,
    ) -> MovieCandidate | None:
        for candidate in self._demo_candidates(recommendation_request, region):
            if self._title_similarity(candidate.title, title) >= (
                FUZZY_REFERENCE_TITLE_THRESHOLD
            ):
                return candidate
        return None

    def _provider_ids(self, providers: list[Provider]) -> list[int]:
        ids: list[int] = []
        for provider in providers:
            ids.extend(PROVIDER_CONFIG[provider].tmdb_ids)
        return ids

    def _provider_names(self, providers: list[Provider]) -> list[str]:
        return [PROVIDER_CONFIG[provider].label for provider in providers]

    def _provider_name_by_id(self, provider_id: int) -> str:
        for provider_config in PROVIDER_CONFIG.values():
            if provider_id in provider_config.tmdb_ids:
                return provider_config.label
        return "Selected provider"

    def _monetization_types(self, recommendation_request: RecommendationRequest) -> str:
        return "|".join(self._monetization_type_list(recommendation_request))

    def _monetization_type_list(
        self, recommendation_request: RecommendationRequest
    ) -> list[str]:
        monetization_types = list(INCLUDED_MONETIZATION_TYPES)
        if recommendation_request.allow_extra_costs:
            monetization_types.extend(PAID_MONETIZATION_TYPES)
        return monetization_types

    def _region(self, recommendation_request: RecommendationRequest) -> str:
        return recommendation_request.region or self.settings.tmdb_region.upper()

    def _language(self, recommendation_request: RecommendationRequest, region: str) -> str:
        if recommendation_request.language == "en" and region == "GB":
            return "en-GB"
        return LANGUAGE_LOCALES[recommendation_request.language]

    def _passes_quality_threshold(self, movie: dict) -> bool:
        rating = movie.get("vote_average")
        vote_count = movie.get("vote_count")
        if rating is None or vote_count is None:
            return False
        return (
            float(rating) >= self.settings.tmdb_min_vote_average
            and int(vote_count) >= self.settings.tmdb_min_vote_count
        )

    def _candidate_passes_quality_threshold(self, candidate: MovieCandidate) -> bool:
        if candidate.rating is None or candidate.vote_count is None:
            return False
        return (
            candidate.rating >= self.settings.tmdb_min_vote_average
            and candidate.vote_count >= self.settings.tmdb_min_vote_count
        )

    def _with_region(self, candidate: MovieCandidate, region: str) -> MovieCandidate:
        return candidate.model_copy(
            update={
                "watch_link": f"https://www.themoviedb.org/movie/{candidate.tmdb_id}/watch?locale={region}"
            }
        )

    def _best_reference_seed(self, movies: Sequence[dict], query: str) -> dict | None:
        ranked = self._rank_reference_seeds(movies, query)
        return ranked[0] if ranked else None

    def _rank_reference_seeds(
        self,
        movies: Sequence[dict],
        query: str,
    ) -> list[dict]:
        def score(movie: dict) -> tuple[int, float, float, int, float]:
            title_similarity = self._movie_title_similarity(movie, query)
            return (
                int(title_similarity >= FUZZY_REFERENCE_TITLE_THRESHOLD),
                title_similarity,
                float(movie.get("vote_average") or 0),
                int(movie.get("vote_count") or 0),
                float(movie.get("popularity") or 0),
            )

        return sorted(movies, key=score, reverse=True)

    def _is_plausible_title_match(self, movie: dict, query: str) -> bool:
        return self._movie_title_similarity(movie, query) >= (
            FUZZY_REFERENCE_TITLE_THRESHOLD
        )

    def _movie_title_similarity(self, movie: dict, query: str) -> float:
        titles = [
            movie.get("title") or "",
            movie.get("original_title") or "",
        ]
        return max(
            (self._title_similarity(title, query) for title in titles if title),
            default=0.0,
        )

    def _is_excluded_candidate(
        self,
        candidate: MovieCandidate,
        excluded_tmdb_ids: set[int],
        excluded_titles: set[str],
    ) -> bool:
        if candidate.tmdb_id in excluded_tmdb_ids:
            return True

        title = self._normalized_text(candidate.title)
        return any(
            self._is_same_reference_title(title, excluded_title)
            for excluded_title in excluded_titles
        )

    def _excluded_movie_titles(
        self,
        recommendation_request: RecommendationRequest,
    ) -> set[str]:
        return {
            self._normalized_text(title)
            for title in recommendation_request.excluded_movie_titles
            if title.strip()
        }

    def _is_same_reference_title(self, title: str, reference_title: str) -> bool:
        if not title or not reference_title:
            return False
        if title == reference_title:
            return True
        if min(len(title), len(reference_title)) < MIN_FUZZY_REFERENCE_LENGTH:
            return False

        return self._title_similarity(title, reference_title) >= (
            FUZZY_REFERENCE_TITLE_THRESHOLD
        )

    def _title_similarity(self, title: str, reference_title: str) -> float:
        normalized_title = self._compact_normalized_text(title)
        normalized_reference = self._compact_normalized_text(reference_title)
        if not normalized_title or not normalized_reference:
            return 0.0

        return SequenceMatcher(None, normalized_title, normalized_reference).ratio()

    def _reference_queries(
        self,
        recommendation_request: RecommendationRequest,
    ) -> list[str]:
        text = self._request_text(recommendation_request)
        candidates: list[str] = []

        for quoted in re.findall(r'"([^"]{2,80})"|\'([^\']{2,80})\'', text):
            candidates.extend(part for part in quoted if part)

        for pattern in REFERENCE_PATTERNS:
            candidates.extend(
                match.group(1)
                for match in re.finditer(pattern, text, flags=re.IGNORECASE)
            )

        first_clause = re.split(r"[,.;:\n]", text, maxsplit=1)[0]
        if self._looks_like_title_reference(first_clause):
            candidates.append(first_clause)

        return self._clean_reference_queries(candidates)

    def _similarity_reference_queries(
        self,
        recommendation_request: RecommendationRequest,
    ) -> list[str]:
        candidates: list[str] = []
        text = self._request_text(recommendation_request)

        for pattern in SIMILARITY_REFERENCE_PATTERNS:
            candidates.extend(
                match.group(1)
                for match in re.finditer(pattern, text, flags=re.IGNORECASE)
            )

        return self._clean_reference_queries(candidates)

    def _clean_reference_queries(self, candidates: Iterable[str]) -> list[str]:
        return list(
            dict.fromkeys(
                cleaned
                for candidate in candidates
                if (cleaned := self._clean_reference_query(candidate))
            )
        )

    def _looks_like_title_reference(self, value: str) -> bool:
        cleaned = self._clean_reference_query(value)
        if not cleaned:
            return False

        normalized = self._normalized_text(cleaned)
        if (
            " like " in f" {normalized} "
            or normalized.startswith("similar to ")
            or normalized.startswith("in the mood for ")
        ):
            return False
        words = normalized.split()
        if len(words) > 6:
            return False
        if all(word in GENERIC_REFERENCE_WORDS for word in words):
            return False
        if any(term == normalized for term in CLASSIC_INTENT_TERMS):
            return False

        starts_title_cased = cleaned[:1].isupper()
        is_short_distinct_phrase = len(words) <= 3 and any(
            word not in GENERIC_REFERENCE_WORDS for word in words
        )
        return starts_title_cased or is_short_distinct_phrase

    def _clean_reference_query(self, value: str) -> str:
        cleaned = re.sub(
            r"^(?:let'?s\s+say(?:\s+for\s+(?:instance|example))?|"
            r"for\s+(?:instance|example)|say|por\s+ejemplo|digamos(?:\s+que)?|"
            r"por\s+decir(?:\s+algo)?|tipo)\s+",
            "",
            value.strip(),
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(with|for|but|and|that|which|please|tonight|para|pero|"
            r"por\s+favor|esta\s+noche|hoy)\b.*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = cleaned.strip(" \"'()[]{}!?")
        if len(cleaned) < 2 or len(cleaned) > 80:
            return ""
        return cleaned

    def _has_classic_intent(
        self,
        recommendation_request: RecommendationRequest,
    ) -> bool:
        normalized = self._normalized_text(self._request_text(recommendation_request))
        return any(term in normalized for term in CLASSIC_INTENT_TERMS)

    def _request_text(self, recommendation_request: RecommendationRequest) -> str:
        return " ".join(
            part
            for part in [
                recommendation_request.mood,
                recommendation_request.group_context or "",
                recommendation_request.notes or "",
            ]
            if part
        )

    def _normalized_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", ascii_value.lower()).strip()

    def _compact_normalized_text(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", self._normalized_text(value))

    def _release_year(self, candidate: MovieCandidate) -> int | None:
        if not candidate.release_year:
            return None
        try:
            return int(candidate.release_year)
        except ValueError:
            return None

    def _dedupe_movies(self, movies: Iterable[dict]) -> Iterable[dict]:
        seen: set[int] = set()
        for movie in movies:
            movie_id = movie.get("id")
            if not movie_id or movie_id in seen:
                continue
            seen.add(movie_id)
            yield movie

    def _dedupe_candidates(
        self,
        candidates: Sequence[MovieCandidate],
    ) -> list[MovieCandidate]:
        deduped: dict[int, MovieCandidate] = {}
        for candidate in candidates:
            existing = deduped.get(candidate.tmdb_id)
            if existing is None:
                deduped[candidate.tmdb_id] = candidate
                continue

            provider_names = list(
                dict.fromkeys([*existing.provider_names, *candidate.provider_names])
            )
            deduped[candidate.tmdb_id] = existing.model_copy(
                update={"provider_names": provider_names}
            )

        return list(deduped.values())

    def _candidate_limit(self) -> int:
        return max(1, min(self.settings.tmdb_candidate_limit, 100))
