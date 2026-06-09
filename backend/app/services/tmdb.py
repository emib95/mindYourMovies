from dataclasses import dataclass

import httpx

from app.config import Settings
from app.schemas import MovieCandidate, Provider, RecommendationRequest


@dataclass(frozen=True)
class ProviderConfig:
    label: str
    tmdb_ids: tuple[int, ...]


PROVIDER_CONFIG: dict[Provider, ProviderConfig] = {
    Provider.netflix: ProviderConfig("Netflix", (8,)),
    Provider.disney: ProviderConfig("Disney+", (337,)),
    Provider.prime: ProviderConfig("Prime Video", (9, 119)),
    Provider.youtube: ProviderConfig("YouTube", (192,)),
    Provider.hbo: ProviderConfig("HBO / NOW", (39, 384, 1899)),
}

INCLUDED_MONETIZATION_TYPES = ("flatrate", "free", "ads")
PAID_MONETIZATION_TYPES = ("rent", "buy")


DEMO_CANDIDATES = [
    MovieCandidate(
        tmdb_id=550,
        title="Fight Club",
        overview="An insomniac office worker and a soap maker form an underground fight club that spirals into something much larger.",
        release_year="1999",
        rating=8.4,
        provider_names=["Netflix"],
        watch_link="https://www.themoviedb.org/movie/550/watch?locale=GB",
    ),
    MovieCandidate(
        tmdb_id=324857,
        title="Spider-Man: Into the Spider-Verse",
        overview="Teen Miles Morales becomes Spider-Man and joins heroes from across the multiverse.",
        release_year="2018",
        rating=8.4,
        provider_names=["Disney+"],
        watch_link="https://www.themoviedb.org/movie/324857/watch?locale=GB",
    ),
    MovieCandidate(
        tmdb_id=588228,
        title="The Tomorrow War",
        overview="A family man is drafted into a future war where humanity is losing against a deadly alien species.",
        release_year="2021",
        rating=7.5,
        provider_names=["Prime Video"],
        watch_link="https://www.themoviedb.org/movie/588228/watch?locale=GB",
    ),
    MovieCandidate(
        tmdb_id=157336,
        title="Interstellar",
        overview="Explorers travel through a wormhole in space in an attempt to ensure humanity's survival.",
        release_year="2014",
        rating=8.5,
        provider_names=["YouTube"],
        watch_link="https://www.themoviedb.org/movie/157336/watch?locale=GB",
    ),
]


class TMDbClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = "https://api.themoviedb.org/3"

    async def discover_movies(
        self, recommendation_request: RecommendationRequest
    ) -> list[MovieCandidate]:
        if not self.settings.tmdb_api_key:
            return self._demo_candidates(recommendation_request.providers)

        provider_ids = self._provider_ids(recommendation_request.providers)
        provider_names = self._provider_names(recommendation_request.providers)
        monetization_types = self._monetization_types(recommendation_request)

        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                f"{self.base_url}/discover/movie",
                params={
                    "api_key": self.settings.tmdb_api_key,
                    "include_adult": "false",
                    "include_video": "false",
                    "language": "en-GB",
                    "page": 1,
                    "sort_by": "popularity.desc",
                    "watch_region": self.settings.tmdb_region,
                    "with_watch_monetization_types": monetization_types,
                    "with_watch_providers": "|".join(str(provider_id) for provider_id in provider_ids),
                },
            )
            response.raise_for_status()

        movies = response.json().get("results", [])[:12]
        return [
            MovieCandidate(
                tmdb_id=movie["id"],
                title=movie.get("title") or movie.get("original_title") or "Unknown title",
                overview=movie.get("overview") or "No overview available.",
                release_year=(movie.get("release_date") or "")[:4] or None,
                rating=movie.get("vote_average"),
                provider_names=provider_names,
                watch_link=f"https://www.themoviedb.org/movie/{movie['id']}/watch?locale={self.settings.tmdb_region}",
            )
            for movie in movies
            if movie.get("id")
        ]

    def _demo_candidates(self, providers: list[Provider]) -> list[MovieCandidate]:
        selected_labels = set(self._provider_names(providers))
        matching = [
            candidate
            for candidate in DEMO_CANDIDATES
            if selected_labels.intersection(candidate.provider_names)
        ]
        return matching or DEMO_CANDIDATES

    def _provider_ids(self, providers: list[Provider]) -> list[int]:
        ids: list[int] = []
        for provider in providers:
            ids.extend(PROVIDER_CONFIG[provider].tmdb_ids)
        return ids

    def _provider_names(self, providers: list[Provider]) -> list[str]:
        return [PROVIDER_CONFIG[provider].label for provider in providers]

    def _monetization_types(self, recommendation_request: RecommendationRequest) -> str:
        monetization_types = list(INCLUDED_MONETIZATION_TYPES)
        if recommendation_request.allow_extra_costs:
            monetization_types.extend(PAID_MONETIZATION_TYPES)
        return "|".join(monetization_types)
