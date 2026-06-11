import logging
from time import perf_counter


class StepTimer:
    def __init__(self, logger_name: str, operation: str):
        self.logger = logging.getLogger(logger_name)
        self.operation = operation
        self.started_at = perf_counter()
        self.last_mark_at = self.started_at
        self.steps: list[tuple[str, float]] = []

    def mark(self, step: str, **extra: object) -> None:
        now = perf_counter()
        elapsed_ms = (now - self.last_mark_at) * 1000
        self.last_mark_at = now
        self.steps.append((step, elapsed_ms))
        self.logger.info(
            "%s step=%s elapsed_ms=%.1f%s",
            self.operation,
            step,
            elapsed_ms,
            self._extra_text(extra),
        )

    def finish(self, **extra: object) -> None:
        total_ms = (perf_counter() - self.started_at) * 1000
        step_summary = ", ".join(
            f"{step}={elapsed_ms:.1f}ms" for step, elapsed_ms in self.steps
        )
        self.logger.info(
            "%s total_ms=%.1f steps=[%s]%s",
            self.operation,
            total_ms,
            step_summary,
            self._extra_text(extra),
        )

    def _extra_text(self, extra: dict[str, object]) -> str:
        if not extra:
            return ""
        return " " + " ".join(
            f"{key}={self._format_value(value)}" for key, value in extra.items()
        )

    def _format_value(self, value: object) -> str:
        text = str(value)
        if any(char.isspace() for char in text):
            return repr(text)
        return text
