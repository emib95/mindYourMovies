import unittest

from app.services.llm import RecommendationEngine
from tests.evals.analyze_openai_responses import analyze_response, summarize
from tests.evals.openai_scenarios import (
    SCENARIOS,
    build_candidates,
    build_openai_user_payload,
    build_request,
)


class OpenAIScenarioTests(unittest.TestCase):
    def test_defines_30_unique_openai_request_scenarios(self) -> None:
        self.assertEqual(len(SCENARIOS), 30)
        self.assertEqual(len({scenario.id for scenario in SCENARIOS}), 30)

    def test_each_scenario_builds_valid_request_payload(self) -> None:
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.id):
                request = build_request(scenario)
                candidates = build_candidates(scenario)
                payload = build_openai_user_payload(scenario)

                self.assertGreaterEqual(len(request.providers), 1)
                self.assertGreaterEqual(len(candidates), 1)
                self.assertEqual(payload["user_answers"], request.model_dump(mode="json"))
                self.assertEqual(
                    payload["candidates"],
                    [candidate.model_dump(mode="json") for candidate in candidates],
                )

    def test_offline_fallback_responses_are_analyzable(self) -> None:
        engine = RecommendationEngine(settings=type("Settings", (), {"openai_api_key": None})())

        results = []
        for scenario in SCENARIOS:
            request = build_request(scenario)
            candidates = build_candidates(scenario)
            response = engine._fallback_recommendation(request, candidates)
            checks, selected = analyze_response(response, candidates)

            self.assertIsNotNone(selected)
            self.assertTrue(checks["required_fields_present"])
            self.assertTrue(checks["movie_title_in_candidates"])
            self.assertTrue(checks["watch_link_matches_candidate"])
            self.assertTrue(checks["provider_matches_candidate"])
            self.assertFalse(checks["not_deterministic_fallback"])

            results.append(
                type(
                    "ScenarioAnalysis",
                    (),
                    {
                        "scenario_id": scenario.id,
                        "checks": checks,
                    },
                )()
            )

        summary = summarize(results)
        self.assertEqual(summary["total_scenarios"], 30)
        self.assertEqual(summary["fully_valid_responses"], 30)
        self.assertEqual(summary["fallback_responses"], 30)


if __name__ == "__main__":
    unittest.main()
