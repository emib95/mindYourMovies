import logging
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.recommendation_trace import RecommendationTracer, clear_trace, get_trace, start_trace
from app.schemas import Provider, RecommendationRequest, RecommendationResponse
from app.services.llm import LLMRecommendationSuggestion, RecommendationEngine
from app.services.tmdb import TMDbClient


class ListLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class RecommendationTracerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = ListLogHandler()
        logger = logging.getLogger("mindyourmovies.recommendation")
        logger.handlers = []
        logger.addHandler(self.handler)
        logger.setLevel(logging.INFO)

    def tearDown(self) -> None:
        clear_trace()
        logging.getLogger("mindyourmovies.recommendation").handlers = []

    def test_stage_records_duration_and_outcome(self) -> None:
        tracer = start_trace("test")
        with tracer.stage("openai_suggest_movies", batch=1) as details:
            details["suggestion_count"] = 5
        tracer.finish("ok", movie_title="Example")

        messages = "\n".join(self.handler.messages)
        self.assertIn("stage=openai_suggest_movies", messages)
        self.assertIn("duration_ms=", messages)
        self.assertIn("suggestion_count", messages)
        self.assertIn("recommendation complete path=test outcome=ok", messages)
        self.assertIn("recommendation summary", messages)

    def test_failed_stage_records_error(self) -> None:
        tracer = start_trace("test")
        with self.assertRaises(RuntimeError):
            with tracer.stage("tmdb_title_verification", requested_title="Missing"):
                raise RuntimeError("lookup failed")

        messages = "\n".join(self.handler.messages)
        self.assertIn("outcome=failed", messages)
        self.assertIn("lookup failed", messages)


class RecommendationFlowLoggingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.handler = ListLogHandler()
        logger = logging.getLogger("mindyourmovies.recommendation")
        logger.handlers = []
        logger.addHandler(self.handler)
        logger.setLevel(logging.INFO)

    def tearDown(self) -> None:
        clear_trace()
        logging.getLogger("mindyourmovies.recommendation").handlers = []

    async def test_llm_first_flow_logs_openai_tmdb_and_link_stages(self) -> None:
        request = RecommendationRequest(
            providers=[Provider.netflix],
            mood="funny and light",
            region="GB",
        )
        suggestion = LLMRecommendationSuggestion(
            movie_title="Fight Club",
            provider="Netflix",
            watch_link="https://www.themoviedb.org/movie/550/watch",
            reason="Bold and intense.",
            why_recommended="Matches the mood.",
        )
        candidate = TMDbClient(Settings(tmdb_api_key=None))._demo_candidate_for_title(
            "Fight Club",
            request,
            "GB",
        )
        assert candidate is not None

        engine = RecommendationEngine(Settings(openai_api_key=None))

        async def fake_suggest(
            recommendation_request: RecommendationRequest,
            excluded_titles: set[str],
            batch_index: int = 1,
        ) -> list[LLMRecommendationSuggestion]:
            trace = get_trace()
            if trace is not None:
                with trace.stage("openai_suggest_movies", batch=batch_index) as details:
                    details["suggestion_count"] = 1
            return [suggestion]

        engine.suggest_movies = AsyncMock(side_effect=fake_suggest)

        tracer = start_trace("test_llm_first")
        try:
            with tracer.stage("llm_first_path", timeout_seconds=60) as details:
                suggestions = await engine.suggest_movies(request, set(), batch_index=1)
                self.assertEqual(len(suggestions), 1)
                verified = await TMDbClient(Settings(tmdb_api_key=None)).available_candidate_for_title(
                    suggestions[0].movie_title,
                    request,
                    batch_index=1,
                    suggestion_index=1,
                )
                self.assertIsNotNone(verified)
                await engine.recommendation_from_suggestion(
                    request,
                    suggestions[0],
                    verified,
                )
                details["result"] = "matched"
            tracer.finish("ok", path_used="llm_first", movie_title=candidate.title)
        finally:
            clear_trace()

        messages = "\n".join(self.handler.messages)
        self.assertIn("stage=openai_suggest_movies", messages)
        self.assertIn("stage=tmdb_title_verification", messages)
        self.assertIn("stage=link_verification", messages)
        self.assertIn("recommendation complete", messages)

    async def test_tmdb_verification_failure_is_logged(self) -> None:
        tracer = start_trace("test_verification_failure")
        client = TMDbClient(Settings(tmdb_api_key=None))
        request = RecommendationRequest(
            providers=[Provider.disney],
            mood="funny and light",
            region="GB",
        )

        result = await client.available_candidate_for_title(
            "Fight Club",
            request,
            batch_index=1,
            suggestion_index=1,
        )
        tracer.finish("failed", reason="verification_failed")

        self.assertIsNone(result)
        messages = "\n".join(self.handler.messages)
        self.assertIn("stage=tmdb_title_verification", messages)
        self.assertIn("'result': 'failed'", messages)


class RecommendationEndpointLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = ListLogHandler()
        logger = logging.getLogger("mindyourmovies.recommendation")
        logger.handlers = []
        logger.addHandler(self.handler)
        logger.setLevel(logging.INFO)

    def tearDown(self) -> None:
        clear_trace()
        logging.getLogger("mindyourmovies.recommendation").handlers = []

    def test_endpoint_logs_request_and_completion(self) -> None:
        response_payload = {
            "movie_title": "Fight Club",
            "provider": "Netflix",
            "watch_link": "https://www.netflix.com/search?q=Fight+Club",
            "reason": "Bold and intense.",
            "why_recommended": "Matches the mood.",
            "tmdb_id": 550,
            "region": "GB",
            "language": "en",
        }

        with patch(
            "app.main._try_llm_first_recommendation",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.main._tmdb_first_recommendation",
            new=AsyncMock(return_value=RecommendationResponse(**response_payload)),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/recommendations",
                json={
                    "providers": ["netflix"],
                    "mood": "something intense",
                    "region": "GB",
                },
            )

        self.assertEqual(response.status_code, 200)
        messages = "\n".join(self.handler.messages)
        self.assertIn("event=request_received", messages)
        self.assertIn("path_used': 'tmdb_first'", messages)
        self.assertIn("recommendation complete", messages)


if __name__ == "__main__":
    unittest.main()
