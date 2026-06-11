import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger("mindyourmovies.recommendation")

_current_trace: ContextVar["RecommendationTracer | None"] = ContextVar(
    "recommendation_trace",
    default=None,
)


@dataclass
class StageRecord:
    name: str
    duration_ms: float
    outcome: str
    details: dict[str, Any] = field(default_factory=dict)


class RecommendationTracer:
    def __init__(self, path: str) -> None:
        self.path = path
        self.stages: list[StageRecord] = []
        self.started_at = time.perf_counter()

    @contextmanager
    def stage(self, name: str, **start_details: Any) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        outcome = "ok"
        details = dict(start_details)
        try:
            yield details
        except Exception as exc:
            outcome = "failed"
            details["error"] = str(exc)
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            record = StageRecord(name, duration_ms, outcome, details)
            self.stages.append(record)
            logger.info(
                "recommendation stage=%s outcome=%s duration_ms=%.1f details=%s",
                name,
                outcome,
                duration_ms,
                details,
            )

    def event(self, name: str, outcome: str, **details: Any) -> None:
        record = StageRecord(name, 0.0, outcome, details)
        self.stages.append(record)
        logger.info(
            "recommendation event=%s outcome=%s details=%s",
            name,
            outcome,
            details,
        )

    def finish(self, outcome: str, **details: Any) -> None:
        total_ms = (time.perf_counter() - self.started_at) * 1000
        logger.info(
            "recommendation complete path=%s outcome=%s total_ms=%.1f stage_count=%s details=%s",
            self.path,
            outcome,
            total_ms,
            len(self.stages),
            details,
        )
        for index, stage in enumerate(self.stages, start=1):
            logger.info(
                "recommendation summary stage=%s/%s name=%s outcome=%s duration_ms=%.1f details=%s",
                index,
                len(self.stages),
                stage.name,
                stage.outcome,
                stage.duration_ms,
                stage.details,
            )


def start_trace(path: str) -> RecommendationTracer:
    tracer = RecommendationTracer(path)
    _current_trace.set(tracer)
    return tracer


def get_trace() -> RecommendationTracer | None:
    return _current_trace.get()


def clear_trace() -> None:
    _current_trace.set(None)
