"""Watchmode integration.

Watchmode is used for one narrow job: turning a TMDb movie that we have already
verified as available into a regional streaming deep link, so the agentic path
never needs a web search to produce a watch link.
"""

from contextlib import nullcontext

import httpx

from app.config import Settings
from app.recommendation_trace import get_trace


# Watchmode source "type" values. Subscription / free / ad-supported / TV-everywhere
# are included with a normal subscription; rent and buy cost extra.
INCLUDED_SOURCE_TYPES = ("sub", "free", "ads", "tve")
PAID_SOURCE_TYPES = ("rent", "buy")

# Each entry maps a set of recognisable tokens (that may appear in the provider
# name we are given, whether it is our own label like "Prime Video" or a TMDb
# name like "Amazon Prime Video") to the keywords that appear in Watchmode
# source names. We match by substring in both directions, so the same entry
# resolves "Prime Video", "Amazon Prime Video", and "Amazon Prime Video with
# Ads" to the same Watchmode keywords.
PROVIDER_NAME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "netflix": ("netflix",),
    "disney": ("disney",),
    "prime": ("prime", "amazon"),
    "amazon": ("prime", "amazon"),
    "youtube": ("youtube",),
    "hbo": ("hbo", "max"),
    "max": ("hbo", "max"),
}


class WatchmodeDeeplink:
    def __init__(self, web_url: str, source_name: str, source_type: str) -> None:
        self.web_url = web_url
        self.source_name = source_name
        self.source_type = source_type


class WatchmodeClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.watchmode_base_url.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.settings.watchmode_api_key)

    async def deeplink_for_tmdb_id(
        self,
        client: httpx.AsyncClient,
        tmdb_id: int,
        region: str,
        provider_names: list[str],
        allow_extra_costs: bool,
    ) -> WatchmodeDeeplink | None:
        """Resolve a regional provider deep link for a TMDb movie.

        Returns ``None`` (and logs the reason) when Watchmode is not configured
        or cannot produce a verified link for one of the selected providers.
        """
        trace = get_trace()
        stage = (
            trace.stage(
                "watchmode_deeplink_lookup",
                tmdb_id=tmdb_id,
                region=region,
                provider_names=provider_names,
                allow_extra_costs=allow_extra_costs,
            )
            if trace
            else nullcontext({})
        )

        with stage as details:
            if not self.enabled:
                details["result"] = "skipped"
                details["reason"] = "missing_watchmode_api_key"
                return None

            watchmode_id = await self._watchmode_id_for_tmdb(client, tmdb_id, details)
            if watchmode_id is None:
                details["result"] = "failed"
                details.setdefault("reason", "no_watchmode_title")
                return None

            sources = await self._sources(client, watchmode_id, region, details)
            deeplink = self._best_deeplink(
                sources,
                region,
                provider_names,
                allow_extra_costs,
            )
            if deeplink is None:
                details["result"] = "failed"
                details.setdefault("reason", "no_matching_source")
                return None

            details["result"] = "ok"
            details["source_name"] = deeplink.source_name
            details["source_type"] = deeplink.source_type
            details["web_url"] = deeplink.web_url
            return deeplink

    async def _watchmode_id_for_tmdb(
        self,
        client: httpx.AsyncClient,
        tmdb_id: int,
        details: dict,
    ) -> int | None:
        payload = await self._get_json(
            client,
            "/search/",
            {
                "search_field": "tmdb_movie_id",
                "search_value": tmdb_id,
                "types": "movie",
            },
        )
        results = payload.get("title_results") or []
        details["watchmode_match_count"] = len(results)
        for result in results:
            watchmode_id = result.get("id")
            if watchmode_id:
                details["watchmode_id"] = watchmode_id
                return int(watchmode_id)
        return None

    async def _sources(
        self,
        client: httpx.AsyncClient,
        watchmode_id: int,
        region: str,
        details: dict,
    ) -> list[dict]:
        payload = await self._get_json(
            client,
            f"/title/{watchmode_id}/sources/",
            {"regions": region},
        )
        sources = payload if isinstance(payload, list) else []
        details["source_count"] = len(sources)
        return sources

    def _best_deeplink(
        self,
        sources: list[dict],
        region: str,
        provider_names: list[str],
        allow_extra_costs: bool,
    ) -> WatchmodeDeeplink | None:
        allowed_types = set(INCLUDED_SOURCE_TYPES)
        if allow_extra_costs:
            allowed_types.update(PAID_SOURCE_TYPES)

        match_keywords = self._match_keywords(provider_names)
        # Fail closed: if we cannot recognise any of the selected providers we
        # must not return an arbitrary source. Returning None lets the caller
        # fall back to a provider search link that points at the right service.
        if not match_keywords:
            return None

        best: WatchmodeDeeplink | None = None
        for source in sources:
            if (source.get("region") or "").upper() != region.upper():
                continue
            source_type = (source.get("type") or "").lower()
            if source_type not in allowed_types:
                continue
            source_name = source.get("name") or ""
            normalized_name = source_name.lower()
            if not any(keyword in normalized_name for keyword in match_keywords):
                continue
            web_url = source.get("web_url")
            if not web_url:
                continue

            deeplink = WatchmodeDeeplink(web_url, source_name, source_type)
            # Prefer an included (subscription/free) source over a paid one.
            if source_type in INCLUDED_SOURCE_TYPES:
                return deeplink
            best = best or deeplink

        return best

    @staticmethod
    def _match_keywords(provider_names: list[str]) -> list[str]:
        """Resolve provider names to Watchmode source-name keywords.

        Works whether the name is one of our labels ("Prime Video") or a TMDb
        name ("Amazon Prime Video", "Disney Plus"), by checking each known token
        as a substring of the provider name.
        """
        keywords: list[str] = []
        for provider in provider_names:
            normalized = provider.strip().lower()
            if not normalized:
                continue
            for token, synonyms in PROVIDER_NAME_KEYWORDS.items():
                if token in normalized:
                    keywords.extend(synonyms)
        return list(dict.fromkeys(keywords))

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, object],
    ) -> object:
        response = await client.get(
            f"{self.base_url}{path}",
            params={
                "apiKey": self.settings.watchmode_api_key,
                **params,
            },
        )
        response.raise_for_status()
        return response.json()
