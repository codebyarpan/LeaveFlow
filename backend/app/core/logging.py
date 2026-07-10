"""Structured JSON logs to stdout.

Implements: the spine's *Observability* row — "Structured JSON logs to stdout; a
`/health` endpoint the deployment probes. Metrics and error monitoring are
deferred."

Deferred deliberately, and not to be added here: metrics, error monitoring, log
shipping, request-id propagation. Module 1's NFR set does not require them.
"""

import json
import logging
import sys
from typing import Any


# Everything a LogRecord carries that is NOT caller-supplied `extra=` data. Computed
# from a blank record so the list tracks the stdlib across Python versions, plus the
# two attributes Formatter itself may attach.
_STANDARD_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    """Render a log record as a single line of JSON on stdout.

    stdout, not a file: the container runtime owns log collection. One object per
    line so that a line-oriented collector can parse it without a multiline codec.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # "Structured" must include the caller's structure: everything passed via
        # `extra=` lands on the record as a non-standard attribute. Dropping it
        # would silently discard the very fields (`employee_id`, ...) later
        # stories log for.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger, replacing any handlers.

    Replaces rather than appends: uvicorn installs its own handlers, and leaving
    them attached emits every record twice — once as JSON, once as plain text.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # uvicorn's access and error loggers default to propagate=False with their own
    # handlers. Clear them so their records reach the root handler above as JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
