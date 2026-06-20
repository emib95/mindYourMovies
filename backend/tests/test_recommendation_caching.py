import time
import unittest
from unittest.mock import AsyncMock, patch

import app.main as main
from app.config import Settings
from app.schemas import MovieCandidate, MovieDetails, Provider, RecommendationRequest
from app.services.cache import TTLCache
from app.services.llm import LLMRecommendationSuggestion, RecommendationEngine


def make_request(mood: str = "funny and light", **overrides: object) -> RecommendationRequest:
    base = {
        "providers": [Provider.netflix],
        "mood": mood,
        "region": "GB",
        "language": "en",
    }
    base.update(overrides)
    return RecommendationRequest(**base)


def make_candidate(tmdb_id: int, title: str) -> MovieCandidate:
    return MovieCandidate(
        tmdb_id=tmdb_id,
        title=title,
        overview=f"{title} overview",
        release_year="2010",
        rating=8.0,
        vote_count=5000,
        popularity=50.0,
        provider_names=["Netflix"],
        watch_link=f"https://www.themoviedb.org/movie/{tmdb_id}/watch?locale=GB",
    )


def make_suggestion(title: str, watch_link: str = "", details: bool = False) -> LLMRecommendationSuggestion:
    return LLMRecommendationSuggestion(
        movie_title=title,
        provider="Netflix",
        watch_link=watch_link,
        reason=f"{title} reason",
        why_recommended=f"{title} why",
        movie_details=MovieDetails(intro="An intro.", actors=["A"], imdb_rating="8.0/10", rotten_tomatoes_score="90%")
        if details
        else None,
    )


class TTLCacheTests(unittest.TestCase):
    def test_set_and_get_round_trip(self) -> None:
        cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=4)
        cache.set("a", "value")
        self.assertEqual(cache.get("a"), "value")
        self.assertIsNone(cache.get("missing"))

    def test_entries_expire_after_ttl(self) -> None:
        cache: TTLCache[str] = TTLCache(ttl_seconds=0.05, max_entries=4)
        cache.set("a", "value")
        time.sleep(0.06)
        self.assertIsNone(cache.get("a"))

    def test_lru_eviction_when_over_capacity(self) -> None:
        cache: TTLCache[int] = TTLCache(ttl_seconds=60, max_entries=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # touch a so b is least-recently-used
        cache.set("c", 3)
        self.assertEqual(cache.get("a"), 1)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("c"), 3)


class SuggestionSetParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RecommendationEngine(Settings(openai_api_key="test-key"))

    def test_parses_multiple_enriched_titles(self) -> None:
        payload = {
            "recommendations": [
                {
                    "movie_title": "First",
                    "provider": "Netflix",
                    "watch_link": "https://www.netflix.com/title/1",
                    "reason": "r1",
                    "why_recommended": "w1",
                    "details": {
                        "intro": "Intro one.",
                        "actors": ["Actor One"],
                        "imdb_rating": "8.1/10",
                        "rotten_tomatoes_score": "92%",
                    },
                },
                {
                    "movie_title": "Second",
                    "provider": "Netflix",
                    "watch_link": "",
                    "reason": "r2",
                    "why_recommended": "w2",
                    "details": {
                        "intro": None,
                        "actors": [],
                        "imdb_rating": None,
                        "rotten_tomatoes_score": None,
                    },
                },
            ]
        }

        suggestions = self.engine._parse_suggestion_set(payload, batch_size=3)

        self.assertEqual([s.movie_title for s in suggestions], ["First", "Second"])
        self.assertIsNotNone(suggestions[0].movie_details)
        self.assertEqual(suggestions[0].movie_details.imdb_rating, "8.1/10")
        self.assertIsNone(suggestions[1].movie_details)

    def test_dedupes_and_caps_to_batch_size(self) -> None:
        payload = {
            "recommendations": [
                {"movie_title": "One", "provider": "", "watch_link": "", "reason": "", "why_recommended": "", "details": {"intro": None, "actors": [], "imdb_rating": None, "rotten_tomatoes_score": None}},
                {"movie_title": "one", "provider": "", "watch_link": "", "reason": "", "why_recommended": "", "details": {"intro": None, "actors": [], "imdb_rating": None, "rotten_tomatoes_score": None}},
                {"movie_title": "Two", "provider": "", "watch_link": "", "reason": "", "why_recommended": "", "details": {"intro": None, "actors": [], "imdb_rating": None, "rotten_tomatoes_score": None}},
                {"movie_title": "Three", "provider": "", "watch_link": "", "reason": "", "why_recommended": "", "details": {"intro": None, "actors": [], "imdb_rating": None, "rotten_tomatoes_score": None}},
            ]
        }

        suggestions = self.engine._parse_suggestion_set(payload, batch_size=2)

        self.assertEqual([s.movie_title for s in suggestions], ["One", "Two"])

    def test_returns_empty_on_malformed_payload(self) -> None:
        self.assertEqual(self.engine._parse_suggestion_set({}, batch_size=3), [])
        self.assertEqual(self.engine._parse_suggestion_set({"recommendations": {}}, batch_size=3), [])

    def test_suggestion_prompt_requests_batch_and_details(self) -> None:
        prompt = self.engine._suggest_movies_system_prompt()
        payload = self.engine._suggest_movies_user_payload(make_request(), {"Seen"})

        self.assertIn("max_recommendations", prompt)
        self.assertIn("IMDb", prompt)
        self.assertIn("Rotten Tomatoes", prompt)
        self.assertEqual(payload["max_recommendations"], 3)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeAsyncClient:
    last_methods: list[str] = []

    def __init__(self, *, head_response=None, get_response=None, raise_exc=None, **kwargs) -> None:
        self._head_response = head_response
        self._get_response = get_response
        self._raise_exc = raise_exc

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def head(self, url: str) -> FakeResponse:
        FakeAsyncClient.last_methods.append("head")
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._head_response

    async def get(self, url: str) -> FakeResponse:
        FakeAsyncClient.last_methods.append("get")
        return self._get_response


def client_factory(**responses):
    def factory(*args, **kwargs):
        return FakeAsyncClient(**responses)

    return factory


class LinkValidationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.engine = RecommendationEngine(Settings(openai_api_key="test-key"))
        FakeAsyncClient.last_methods = []

    async def test_reachable_for_ok_status(self) -> None:
        with patch("app.services.llm.httpx.AsyncClient", client_factory(head_response=FakeResponse(200))):
            self.assertTrue(await self.engine._link_is_reachable("https://www.netflix.com/title/1"))

    async def test_unreachable_for_missing_page(self) -> None:
        with patch("app.services.llm.httpx.AsyncClient", client_factory(head_response=FakeResponse(404))):
            self.assertFalse(await self.engine._link_is_reachable("https://www.netflix.com/title/dead"))

    async def test_anti_bot_status_is_still_reachable(self) -> None:
        with patch(
            "app.services.llm.httpx.AsyncClient",
            client_factory(head_response=FakeResponse(403), get_response=FakeResponse(403)),
        ):
            self.assertTrue(await self.engine._link_is_reachable("https://www.disneyplus.com/movies/x/1"))

    async def test_transport_error_is_unreachable(self) -> None:
        import httpx

        with patch(
            "app.services.llm.httpx.AsyncClient",
            client_factory(raise_exc=httpx.ConnectError("boom")),
        ):
            self.assertFalse(await self.engine._link_is_reachable("https://www.netflix.com/title/1"))

    async def test_head_405_falls_back_to_get(self) -> None:
        with patch(
            "app.services.llm.httpx.AsyncClient",
            client_factory(head_response=FakeResponse(405), get_response=FakeResponse(200)),
        ):
            self.assertTrue(await self.engine._link_is_reachable("https://www.primevideo.com/detail/1"))
        self.assertEqual(FakeAsyncClient.last_methods, ["head", "get"])

    async def test_resolve_watch_link_skips_unsupported_without_http(self) -> None:
        suggestion = make_suggestion("First", watch_link="https://www.themoviedb.org/movie/1/watch")
        candidate = make_candidate(1, "First")

        with patch("app.services.llm.httpx.AsyncClient", client_factory(head_response=FakeResponse(200))):
            link = await self.engine.resolve_watch_link(make_request(), suggestion, candidate)

        self.assertIsNone(link)
        self.assertEqual(FakeAsyncClient.last_methods, [])

    async def test_resolve_watch_link_returns_reachable_provider_link(self) -> None:
        suggestion = make_suggestion("First", watch_link="https://www.netflix.com/title/1")
        candidate = make_candidate(1, "First")

        with patch("app.services.llm.httpx.AsyncClient", client_factory(head_response=FakeResponse(200))):
            link = await self.engine.resolve_watch_link(make_request(), suggestion, candidate)

        self.assertEqual(link, "https://www.netflix.com/title/1")

    async def test_resolve_watch_link_rejects_dead_provider_link(self) -> None:
        suggestion = make_suggestion("First", watch_link="https://www.netflix.com/title/dead")
        candidate = make_candidate(1, "First")

        with patch("app.services.llm.httpx.AsyncClient", client_factory(head_response=FakeResponse(404))):
            link = await self.engine.resolve_watch_link(make_request(), suggestion, candidate)

        self.assertIsNone(link)

    def test_build_recommendation_attaches_details(self) -> None:
        suggestion = make_suggestion("First", details=True)
        candidate = make_candidate(1, "First")

        response = self.engine.build_recommendation(
            make_request(),
            suggestion,
            candidate,
            "https://www.netflix.com/title/1",
        )

        self.assertEqual(response.movie_title, "First")
        self.assertIsNotNone(response.movie_details)
        self.assertEqual(response.movie_details.rotten_tomatoes_score, "90%")


class OrchestrationFalloverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        main.recommendation_cache.clear()

    def tearDown(self) -> None:
        main.recommendation_cache.clear()

    async def test_uses_second_movie_when_first_link_is_dead(self) -> None:
        suggestions = [
            make_suggestion("First", watch_link="https://www.netflix.com/title/dead", details=True),
            make_suggestion("Second", watch_link="https://www.netflix.com/title/works", details=True),
        ]
        candidates = {
            "First": make_candidate(1, "First"),
            "Second": make_candidate(2, "Second"),
        }

        async def fake_candidate(title, request, **kwargs):
            return candidates.get(title)

        async def fake_resolve(request, suggestion, candidate):
            return None if candidate.tmdb_id == 1 else suggestion.watch_link

        with patch.object(main.tmdb_client, "available_candidate_for_title", new=AsyncMock(side_effect=fake_candidate)), \
            patch.object(main.recommendation_engine, "resolve_watch_link", new=AsyncMock(side_effect=fake_resolve)):
            response = await main._recommendation_from_suggestions(make_request(), suggestions, batch_index=1)

        self.assertIsNotNone(response)
        self.assertEqual(response.movie_title, "Second")
        self.assertEqual(str(response.watch_link), "https://www.netflix.com/title/works")

    async def test_falls_back_to_search_link_when_all_links_dead(self) -> None:
        suggestions = [make_suggestion("First", watch_link="https://www.netflix.com/title/dead")]

        async def fake_candidate(title, request, **kwargs):
            return make_candidate(1, "First")

        with patch.object(main.tmdb_client, "available_candidate_for_title", new=AsyncMock(side_effect=fake_candidate)), \
            patch.object(main.recommendation_engine, "resolve_watch_link", new=AsyncMock(return_value=None)):
            response = await main._recommendation_from_suggestions(make_request(), suggestions, batch_index=1)

        self.assertIsNotNone(response)
        self.assertEqual(str(response.watch_link), "https://www.netflix.com/search?q=First")

    async def test_already_watched_is_served_from_cache_without_new_search(self) -> None:
        request = make_request()
        cached = [
            make_suggestion("First", watch_link="https://www.netflix.com/title/1", details=True),
            make_suggestion("Second", watch_link="https://www.netflix.com/title/2", details=True),
        ]
        main.recommendation_cache.set(main._recommendation_cache_key(request), cached)

        async def fake_candidate(title, req, **kwargs):
            ids = {"First": 1, "Second": 2}
            return make_candidate(ids[title], title)

        suggest_mock = AsyncMock(return_value=[])
        with patch.object(main.tmdb_client, "available_candidate_for_title", new=AsyncMock(side_effect=fake_candidate)), \
            patch.object(main.recommendation_engine, "resolve_watch_link", new=AsyncMock(side_effect=lambda r, s, c: s.watch_link)), \
            patch.object(main.recommendation_engine, "suggest_movies", new=suggest_mock):
            # First-time user excludes nothing -> gets the main pick from cache.
            first = await main._llm_first_recommendation(request)
            # "I've already watched that" -> exclude First, still served from cache.
            watched_request = request.model_copy(update={"excluded_movie_titles": ["First"]})
            second = await main._llm_first_recommendation(watched_request)

        self.assertEqual(first.movie_title, "First")
        self.assertEqual(second.movie_title, "Second")
        suggest_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
