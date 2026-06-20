import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from app.config import Settings
from app.recommendation_trace import clear_trace, start_trace
from app.schemas import Provider, RecommendationRequest, RecommendationResponse
from app.services.agent import MovieRecommendationAgent, _agent_tools
from app.services.tmdb import TMDbClient
from app.services.watchmode import WatchmodeClient


class ListLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "openai_api_key": "test-key",
        "tmdb_api_key": "test-key",
        "watchmode_api_key": "wm-key",
        "agent_max_iterations": 6,
        **overrides,
    }
    return Settings(**values)


def make_request() -> RecommendationRequest:
    return RecommendationRequest(
        providers=[Provider.netflix],
        mood="A tense, acclaimed thriller",
        region="GB",
        language="en",
    )


def function_call(name: str, arguments: dict, call_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=json.dumps(arguments),
        call_id=call_id,
    )


def model_response(items: list, input_tokens: int = 120, output_tokens: int = 30) -> SimpleNamespace:
    return SimpleNamespace(
        output=items,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class FakeResponses:
    def __init__(self, responses: list) -> None:
        self._responses = responses
        self.call_count = 0

    async def create(self, **kwargs: object) -> object:
        response = self._responses[self.call_count]
        self.call_count += 1
        return response


class FakeOpenAIClient:
    def __init__(self, responses: list) -> None:
        self.responses = FakeResponses(responses)


class AgentToolSchemaTests(unittest.TestCase):
    def test_exposes_expected_tools(self) -> None:
        names = {tool["name"] for tool in _agent_tools()}
        self.assertEqual(
            names,
            {
                "search_movies",
                "discover_movies",
                "movie_details",
                "check_availability",
                "finalize_recommendation",
            },
        )


class WatchmodeDeeplinkTests(unittest.TestCase):
    def test_prefers_included_source_matching_provider(self) -> None:
        client = WatchmodeClient(make_settings())
        sources = [
            {"name": "Apple TV", "type": "rent", "region": "GB", "web_url": "https://tv.apple.com/x"},
            {"name": "Netflix", "type": "sub", "region": "GB", "web_url": "https://www.netflix.com/title/1"},
        ]

        deeplink = client._best_deeplink(sources, "GB", ["Netflix"], allow_extra_costs=False)

        self.assertIsNotNone(deeplink)
        assert deeplink is not None
        self.assertEqual(deeplink.web_url, "https://www.netflix.com/title/1")
        self.assertEqual(deeplink.source_type, "sub")

    def test_skips_paid_source_when_extra_costs_disallowed(self) -> None:
        client = WatchmodeClient(make_settings())
        sources = [
            {"name": "Netflix", "type": "rent", "region": "GB", "web_url": "https://www.netflix.com/title/1"},
        ]

        self.assertIsNone(
            client._best_deeplink(sources, "GB", ["Netflix"], allow_extra_costs=False)
        )
        self.assertIsNotNone(
            client._best_deeplink(sources, "GB", ["Netflix"], allow_extra_costs=True)
        )

    def test_skips_wrong_region(self) -> None:
        client = WatchmodeClient(make_settings())
        sources = [
            {"name": "Netflix", "type": "sub", "region": "US", "web_url": "https://www.netflix.com/title/1"},
        ]

        self.assertIsNone(
            client._best_deeplink(sources, "GB", ["Netflix"], allow_extra_costs=True)
        )

    def test_matches_prime_video_alias(self) -> None:
        client = WatchmodeClient(make_settings())
        sources = [
            {
                "name": "Amazon Prime Video",
                "type": "sub",
                "region": "GB",
                "web_url": "https://www.primevideo.com/detail/1",
            },
        ]

        deeplink = client._best_deeplink(sources, "GB", ["Prime Video"], allow_extra_costs=False)

        self.assertIsNotNone(deeplink)
        assert deeplink is not None
        self.assertEqual(deeplink.source_name, "Amazon Prime Video")


class TMDbAgentToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.handler = ListLogHandler()
        logger = logging.getLogger("mindyourmovies.recommendation")
        logger.handlers = []
        logger.addHandler(self.handler)
        logger.setLevel(logging.INFO)

    def tearDown(self) -> None:
        clear_trace()
        logging.getLogger("mindyourmovies.recommendation").handlers = []

    async def test_discover_trims_results_and_logs_api_call(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/3/discover/movie")
            self.assertEqual(request.url.params.get("with_genres"), "53")
            return httpx.Response(
                200,
                json={
                    "total_results": 1,
                    "results": [
                        {
                            "id": 550,
                            "title": "Fight Club",
                            "original_title": "Fight Club",
                            "release_date": "1999-10-15",
                            "vote_average": 8.4,
                            "vote_count": 28000,
                            "popularity": 70.0,
                            "original_language": "en",
                            "genre_ids": [18, 53],
                            "overview": "An office worker forms a fight club.",
                        }
                    ],
                },
            )

        client = TMDbClient(make_settings())
        start_trace("agent_test")
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
                result = await client.agent_discover_movies(
                    http_client,
                    make_request(),
                    genres=["Thriller"],
                )
        finally:
            clear_trace()

        self.assertEqual(result["results"][0]["tmdb_id"], 550)
        self.assertIn("Thriller", result["results"][0]["genres"])
        messages = "\n".join(self.handler.messages)
        self.assertIn("stage=tmdb_api_call", messages)
        self.assertIn("'tool': 'discover_movies'", messages)

    async def test_movie_details_extracts_cast_and_director(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": 550,
                    "title": "Fight Club",
                    "overview": "An office worker forms a fight club.",
                    "runtime": 139,
                    "genres": [{"id": 18, "name": "Drama"}],
                    "credits": {
                        "cast": [{"name": "Brad Pitt"}, {"name": "Edward Norton"}],
                        "crew": [{"job": "Director", "name": "David Fincher"}],
                    },
                    "keywords": {"keywords": [{"name": "support group"}]},
                },
            )

        client = TMDbClient(make_settings())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            result = await client.agent_movie_details(http_client, make_request(), 550)

        self.assertEqual(result["cast"], ["Brad Pitt", "Edward Norton"])
        self.assertEqual(result["directors"], ["David Fincher"])
        self.assertEqual(result["keywords"], ["support group"])


class AgentLoopTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.handler = ListLogHandler()
        logger = logging.getLogger("mindyourmovies.recommendation")
        logger.handlers = []
        logger.addHandler(self.handler)
        logger.setLevel(logging.INFO)

    def tearDown(self) -> None:
        clear_trace()
        logging.getLogger("mindyourmovies.recommendation").handlers = []

    def _build_agent(self) -> MovieRecommendationAgent:
        settings = make_settings()
        tmdb = TMDbClient(settings)
        tmdb.agent_discover_movies = AsyncMock(
            return_value={
                "results": [
                    {"tmdb_id": 550, "title": "Fight Club", "vote_average": 8.4, "vote_count": 28000}
                ]
            }
        )
        tmdb.agent_movie_details = AsyncMock(
            return_value={
                "tmdb_id": 550,
                "title": "Fight Club",
                "overview": "An office worker forms a fight club.",
                "cast": ["Brad Pitt", "Edward Norton"],
            }
        )
        tmdb.agent_watch_availability = AsyncMock(
            return_value={
                "tmdb_id": 550,
                "available_on_selected_providers": True,
                "providers": ["Netflix"],
            }
        )
        watchmode = WatchmodeClient(settings)
        watchmode.deeplink_for_tmdb_id = AsyncMock(
            return_value=SimpleNamespace(
                web_url="https://www.netflix.com/title/550",
                source_name="Netflix",
                source_type="sub",
            )
        )
        return MovieRecommendationAgent(settings, tmdb, watchmode)

    async def test_loop_finalizes_available_movie_and_logs_tokens(self) -> None:
        agent = self._build_agent()
        responses = [
            model_response([function_call("discover_movies", {"genres": ["Thriller"]}, "c1")]),
            model_response(
                [
                    function_call(
                        "finalize_recommendation",
                        {"tmdb_id": 550, "reason": "A bold thriller.", "why_recommended": "Fits the tense mood."},
                        "c2",
                    )
                ]
            ),
        ]
        client = FakeOpenAIClient(responses)

        tracer = start_trace("agent_test")
        try:
            result = await agent._run_loop(make_request(), client, object())
            tracer.finish("ok", path_used="agent")
        finally:
            clear_trace()

        self.assertIsInstance(result, RecommendationResponse)
        assert isinstance(result, RecommendationResponse)
        self.assertEqual(result.movie_title, "Fight Club")
        self.assertEqual(str(result.watch_link), "https://www.netflix.com/title/550")
        self.assertEqual(result.provider, "Netflix")
        self.assertIsNotNone(result.movie_details)
        assert result.movie_details is not None
        self.assertEqual(result.movie_details.actors, ["Brad Pitt", "Edward Norton"])

        messages = "\n".join(self.handler.messages)
        self.assertIn("stage=agent_llm_turn", messages)
        self.assertIn("input_tokens", messages)
        self.assertIn("total_tokens=", messages)

    async def test_loop_keeps_searching_when_movie_unavailable(self) -> None:
        agent = self._build_agent()
        agent.tmdb.agent_watch_availability = AsyncMock(
            side_effect=[
                {"tmdb_id": 999, "available_on_selected_providers": False, "providers": []},
                {"tmdb_id": 550, "available_on_selected_providers": True, "providers": ["Netflix"]},
            ]
        )
        responses = [
            model_response(
                [
                    function_call(
                        "finalize_recommendation",
                        {"tmdb_id": 999, "reason": "x", "why_recommended": "y"},
                        "c1",
                    )
                ]
            ),
            model_response(
                [
                    function_call(
                        "finalize_recommendation",
                        {"tmdb_id": 550, "reason": "A bold thriller.", "why_recommended": "Fits."},
                        "c2",
                    )
                ]
            ),
        ]
        client = FakeOpenAIClient(responses)

        start_trace("agent_test")
        try:
            result = await agent._run_loop(make_request(), client, object())
        finally:
            clear_trace()

        self.assertIsInstance(result, RecommendationResponse)
        assert isinstance(result, RecommendationResponse)
        self.assertEqual(result.tmdb_id, 550)
        self.assertEqual(client.responses.call_count, 2)

    async def test_loop_returns_none_when_iterations_exhausted(self) -> None:
        agent = self._build_agent()
        # Always asks for details, never finalises.
        responses = [
            model_response([function_call("movie_details", {"tmdb_id": 550}, f"c{i}")])
            for i in range(agent.settings.agent_max_iterations)
        ]
        client = FakeOpenAIClient(responses)

        start_trace("agent_test")
        try:
            result = await agent._run_loop(make_request(), client, object())
        finally:
            clear_trace()

        self.assertIsNone(result)
        messages = "\n".join(self.handler.messages)
        self.assertIn("max_iterations_reached", messages)


if __name__ == "__main__":
    unittest.main()
