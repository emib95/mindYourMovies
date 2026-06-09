import unittest
from unittest.mock import AsyncMock

from app.config import Settings
from app.schemas import RecommendationResponse
from app.services.provider_links import ProviderLinkResolver


def make_recommendation(**overrides: object) -> RecommendationResponse:
    values = {
        "movie_title": "Interstellar",
        "provider": "Netflix",
        "watch_link": "https://www.themoviedb.org/movie/157336/watch?locale=GB",
        "reason": "A strong fit.",
        "why_recommended": "It fits the request.",
        "tmdb_id": 157336,
        "region": "GB",
        "language": "en",
        **overrides,
    }
    return RecommendationResponse(**values)


class ProviderLinkResolverTests(unittest.IsolatedAsyncioTestCase):
    def test_provider_from_name_handles_combined_labels(self) -> None:
        resolver = ProviderLinkResolver(Settings())

        provider_config = resolver._provider_from_name("Netflix, Disney+")

        self.assertIsNotNone(provider_config)
        self.assertEqual(provider_config.name, "Netflix")

    def test_best_link_uses_official_provider_domain(self) -> None:
        resolver = ProviderLinkResolver(Settings())
        provider_config = resolver._provider_from_name("Netflix")
        self.assertIsNotNone(provider_config)

        best_link = resolver._best_link(
            [
                {
                    "name": "Interstellar watch providers",
                    "snippet": "TMDb watch page.",
                    "url": "https://www.themoviedb.org/movie/157336/watch?locale=GB",
                    "displayUrl": "themoviedb.org",
                },
                {
                    "name": "Interstellar | Netflix",
                    "snippet": "Watch Interstellar on Netflix.",
                    "url": "https://www.netflix.com/title/70305903",
                    "displayUrl": "netflix.com/title/70305903",
                },
            ],
            "Interstellar",
            provider_config,
        )

        self.assertEqual(best_link, "https://www.netflix.com/title/70305903")

    def test_best_link_rejects_youtube_trailer_results(self) -> None:
        resolver = ProviderLinkResolver(Settings())
        provider_config = resolver._provider_from_name("YouTube")
        self.assertIsNotNone(provider_config)

        best_link = resolver._best_link(
            [
                {
                    "name": "Interstellar Official Trailer - YouTube",
                    "snippet": "Watch the official trailer.",
                    "url": "https://www.youtube.com/watch?v=example",
                    "displayUrl": "youtube.com/watch",
                }
            ],
            "Interstellar",
            provider_config,
        )

        self.assertIsNone(best_link)

    async def test_resolve_keeps_tmdb_link_without_bing_key(self) -> None:
        resolver = ProviderLinkResolver(Settings(bing_search_api_key=None))
        recommendation = make_recommendation()

        resolved = await resolver.resolve(recommendation)

        self.assertEqual(resolved.watch_link, recommendation.watch_link)

    async def test_resolve_replaces_link_with_confident_provider_result(self) -> None:
        resolver = ProviderLinkResolver(Settings(bing_search_api_key="test-key"))
        resolver._search_provider_link = AsyncMock(
            return_value="https://www.netflix.com/title/70305903"
        )
        recommendation = make_recommendation()

        resolved = await resolver.resolve(recommendation)

        self.assertEqual(str(resolved.watch_link), "https://www.netflix.com/title/70305903")


if __name__ == "__main__":
    unittest.main()
