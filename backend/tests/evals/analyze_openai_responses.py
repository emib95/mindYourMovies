"""Run the 30 OpenAI recommendation scenarios and summarize responses.

Usage from ``backend/``:

    python -m tests.evals.analyze_openai_responses --live

Without ``--live`` this uses the app's deterministic fallback path, which is
useful for validating the harness without making OpenAI API calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.config import Settings
from app.schemas import MovieCandidate, RecommendationResponse
from app.services.llm import RecommendationEngine
from tests.evals.openai_scenarios import (
    SCENARIOS,
    OpenAIScenario,
    build_candidates,
    build_request,
)


FALLBACK_REASON = "Picked from available UK candidates using your provider and mood answers."


@dataclass(frozen=True)
class ScenarioAnalysis:
    scenario_id: str
    description: str
    mode: str
    elapsed_ms: int
    response: dict[str, Any]
    checks: dict[str, bool]
    selected_candidate: dict[str, Any] | None


def analyze_response(
    response: RecommendationResponse,
    candidates: list[MovieCandidate],
) -> tuple[dict[str, bool], MovieCandidate | None]:
    selected = _candidate_by_title(candidates, response.movie_title)
    normalized_response_provider = _normalize_provider(response.provider)
    normalized_candidate_providers = (
        {_normalize_provider(provider) for provider in selected.provider_names}
        if selected
        else set()
    )
    checks = {
        "required_fields_present": all(
            [
                bool(response.movie_title),
                bool(response.provider),
                bool(str(response.watch_link)),
                bool(response.reason),
            ]
        ),
        "movie_title_in_candidates": selected is not None,
        "watch_link_matches_candidate": (
            selected is not None and str(response.watch_link) == str(selected.watch_link)
        ),
        "provider_matches_candidate": (
            selected is not None
            and any(
                normalized_response_provider == candidate_provider
                or normalized_response_provider in candidate_provider
                or candidate_provider in normalized_response_provider
                for candidate_provider in normalized_candidate_providers
            )
        ),
        "not_deterministic_fallback": response.reason != FALLBACK_REASON,
    }
    return checks, selected


async def run_scenario(
    scenario: OpenAIScenario,
    *,
    live: bool,
    model: str,
    api_key: str | None,
    region: str,
) -> ScenarioAnalysis:
    settings = Settings(
        openai_api_key=api_key if live else None,
        openai_model=model,
        tmdb_region=region,
    )
    engine = RecommendationEngine(settings)
    request = build_request(scenario)
    candidates = build_candidates(scenario)

    started = time.perf_counter()
    response = await engine.recommend(request, candidates)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    checks, selected = analyze_response(response, candidates)

    return ScenarioAnalysis(
        scenario_id=scenario.id,
        description=scenario.description,
        mode="live-openai" if live else "offline-fallback",
        elapsed_ms=elapsed_ms,
        response=response.model_dump(mode="json"),
        checks=checks,
        selected_candidate=selected.model_dump(mode="json") if selected else None,
    )


async def run_all(
    *,
    live: bool,
    model: str,
    api_key: str | None,
    region: str,
    limit: int | None,
) -> list[ScenarioAnalysis]:
    selected_scenarios = SCENARIOS[:limit] if limit is not None else SCENARIOS
    results: list[ScenarioAnalysis] = []
    for scenario in selected_scenarios:
        results.append(
            await run_scenario(
                scenario,
                live=live,
                model=model,
                api_key=api_key,
                region=region,
            )
        )
    return results


def summarize(results: list[ScenarioAnalysis]) -> dict[str, Any]:
    total = len(results)
    check_names = sorted({name for result in results for name in result.checks})
    passed_by_check = {
        check_name: sum(1 for result in results if result.checks.get(check_name))
        for check_name in check_names
    }
    fully_valid = sum(
        1
        for result in results
        if all(
            passed
            for name, passed in result.checks.items()
            if name != "not_deterministic_fallback"
        )
    )
    fallback_count = sum(
        1 for result in results if not result.checks["not_deterministic_fallback"]
    )

    return {
        "total_scenarios": total,
        "fully_valid_responses": fully_valid,
        "fallback_responses": fallback_count,
        "passed_by_check": passed_by_check,
        "failed_scenarios": [
            result.scenario_id
            for result in results
            if any(
                not passed
                for name, passed in result.checks.items()
                if name != "not_deterministic_fallback"
            )
        ],
    }


def parse_args() -> argparse.Namespace:
    configured_settings = Settings()
    parser = argparse.ArgumentParser(
        description="Analyze recommendation responses for 30 OpenAI API scenarios."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call OpenAI using OPENAI_API_KEY instead of the deterministic fallback.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL") or configured_settings.openai_model,
        help="OpenAI model to use for live calls.",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("TMDB_REGION") or configured_settings.tmdb_region,
        help="Region included in the OpenAI user payload.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N scenarios.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for the full JSON report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configured_settings = Settings()
    api_key = os.getenv("OPENAI_API_KEY") or configured_settings.openai_api_key
    if args.live and not api_key:
        raise SystemExit("OPENAI_API_KEY is required when using --live.")

    results = asyncio.run(
        run_all(
            live=args.live,
            model=args.model,
            api_key=api_key,
            region=args.region,
            limit=args.limit,
        )
    )
    report = {
        "mode": "live-openai" if args.live else "offline-fallback",
        "model": args.model,
        "summary": summarize(results),
        "results": [asdict(result) for result in results],
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report["summary"], indent=2))


def _candidate_by_title(
    candidates: list[MovieCandidate],
    title: str,
) -> MovieCandidate | None:
    normalized_title = title.strip().lower()
    for candidate in candidates:
        if candidate.title.lower() == normalized_title:
            return candidate
    return None


def _normalize_provider(provider: str) -> str:
    return (
        provider.lower()
        .replace("+", " plus")
        .replace("/", " ")
        .replace(",", " ")
        .replace("  ", " ")
        .strip()
    )


if __name__ == "__main__":
    main()
