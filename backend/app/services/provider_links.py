from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.schemas import RecommendationResponse


@dataclass(frozen=True)
class ProviderLinkConfig:
    name: str
    aliases: tuple[str, ...]
    query_label: str
    domains: tuple[str, ...]
    path_markers: tuple[str, ...] = ()
    excluded_terms: tuple[str, ...] = ()


PROVIDER_LINK_CONFIGS = (
    ProviderLinkConfig(
        name="Netflix",
        aliases=("netflix",),
        query_label="Netflix",
        domains=("netflix.com",),
        path_markers=("/title/", "/watch/"),
    ),
    ProviderLinkConfig(
        name="Disney+",
        aliases=("disney", "disney+"),
        query_label="Disney+",
        domains=("disneyplus.com",),
        path_markers=("/movies/", "/browse/entity-"),
    ),
    ProviderLinkConfig(
        name="Prime Video",
        aliases=("prime video", "amazon prime", "prime"),
        query_label="Prime Video",
        domains=("primevideo.com", "amazon."),
        path_markers=("/detail/", "/gp/video/"),
    ),
    ProviderLinkConfig(
        name="YouTube",
        aliases=("youtube", "youtube movies"),
        query_label="YouTube Movies",
        domains=("youtube.com", "youtu.be"),
        path_markers=("/watch", "/movie"),
        excluded_terms=("trailer", "clip", "behind the scenes", "featurette"),
    ),
    ProviderLinkConfig(
        name="HBO / NOW",
        aliases=("hbo", "now", "now tv", "nowtv", "max", "hbo max"),
        query_label="Max HBO NOW",
        domains=("max.com", "hbomax.com", "nowtv.com", "hbo.com"),
        path_markers=("/movies/", "/movie/", "/watch/"),
    ),
)


class ProviderLinkResolver:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def resolve(
        self,
        recommendation: RecommendationResponse,
    ) -> RecommendationResponse:
        if (
            not self.settings.provider_link_search_enabled
            or not self.settings.bing_search_api_key
        ):
            return recommendation

        provider_config = self._provider_from_name(recommendation.provider)
        if provider_config is None:
            return recommendation

        try:
            link = await self._search_provider_link(
                recommendation.movie_title,
                recommendation.region,
                provider_config,
            )
        except httpx.HTTPError:
            return recommendation

        if link is None:
            return recommendation

        return recommendation.model_copy(update={"watch_link": link})

    async def _search_provider_link(
        self,
        movie_title: str,
        region: str,
        provider_config: ProviderLinkConfig,
    ) -> str | None:
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.get(
                self.settings.bing_search_endpoint,
                headers={
                    "Ocp-Apim-Subscription-Key": self.settings.bing_search_api_key,
                },
                params={
                    "q": self._query(movie_title, region, provider_config),
                    "count": 8,
                    "mkt": self._market(region),
                    "responseFilter": "Webpages",
                    "safeSearch": "Moderate",
                    "textDecorations": "false",
                    "textFormat": "Raw",
                },
            )
            response.raise_for_status()

        return self._best_link(
            response.json().get("webPages", {}).get("value", []),
            movie_title,
            provider_config,
        )

    def _best_link(
        self,
        results: list[dict],
        movie_title: str,
        provider_config: ProviderLinkConfig,
    ) -> str | None:
        scored_links = [
            (score, result.get("url"))
            for result in results
            if (score := self._result_score(result, movie_title, provider_config)) > 0
        ]
        if not scored_links:
            return None

        scored_links.sort(reverse=True)
        return scored_links[0][1]

    def _result_score(
        self,
        result: dict,
        movie_title: str,
        provider_config: ProviderLinkConfig,
    ) -> int:
        url = str(result.get("url") or "")
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            return 0
        if not self._host_matches(parsed_url.netloc, provider_config):
            return 0

        searchable = " ".join(
            str(result.get(key) or "").lower()
            for key in ("name", "snippet", "displayUrl", "url")
        )
        if any(term in searchable for term in provider_config.excluded_terms):
            return 0

        title_tokens = [
            token
            for token in self._normalized_tokens(movie_title)
            if len(token) > 2
        ]
        if title_tokens and not any(token in searchable for token in title_tokens):
            return 0

        path = parsed_url.path.lower()
        score = 100
        if any(marker in path for marker in provider_config.path_markers):
            score += 30
        score += sum(1 for token in title_tokens if token in searchable)
        return score

    def _provider_from_name(self, provider_name: str) -> ProviderLinkConfig | None:
        normalized_provider = provider_name.lower()
        for provider_config in PROVIDER_LINK_CONFIGS:
            if any(alias in normalized_provider for alias in provider_config.aliases):
                return provider_config
        return None

    def _query(
        self,
        movie_title: str,
        region: str,
        provider_config: ProviderLinkConfig,
    ) -> str:
        domain_query = " OR ".join(
            f"site:{domain}"
            for domain in provider_config.domains
            if not domain.endswith(".")
        )
        query_parts = [
            f'"{movie_title}"',
            provider_config.query_label,
            "watch",
            region.upper(),
        ]
        if domain_query:
            query_parts.append(f"({domain_query})")
        return " ".join(query_parts)

    def _market(self, region: str) -> str:
        region = region.upper()
        if region == "GB":
            return "en-GB"
        if region == "ES":
            return "es-ES"
        return f"en-{region}"

    def _host_matches(
        self,
        netloc: str,
        provider_config: ProviderLinkConfig,
    ) -> bool:
        host = netloc.lower().removeprefix("www.").split(":")[0]
        return any(
            host == domain
            or host.endswith(f".{domain}")
            or (domain.endswith(".") and host.startswith(domain))
            for domain in provider_config.domains
        )

    def _normalized_tokens(self, value: str) -> list[str]:
        return [
            token
            for token in "".join(
                character.lower() if character.isalnum() else " "
                for character in value
            ).split()
            if token
        ]
