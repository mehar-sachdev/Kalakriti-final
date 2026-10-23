"""Logging setup with secret redaction.

Nothing that looks like a credential is ever written to the console or log file:
* URLs of the form scheme://user:PASSWORD@host are masked,
* ``Bearer <token>`` headers are masked,
* any literal secret registered through :func:`register_secret` is masked.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRETS: set[str] = set()
_PATTERNS = [
    (re.compile(r"([a-zA-Z][a-zA-Z0-9+.\-]*://[^:/\s@]+:)([^@\s]+)(@)"), r"\1***\3"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-~+/=]{8,}"), r"\1***"),
    (re.compile(r"(?i)((?:api[_-]?key|token|password|secret)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;]{6,}"), r"\1***"),
]


def register_secret(value: str | None) -> None:
    if value and len(value) >= 6:
        _SECRETS.add(value)


def redact(text: str) -> str:
    for secret in _SECRETS:
        text = text.replace(secret, "***")
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            message = str(record.msg)
        record.msg = redact(message)
        record.args = ()
        if record.exc_info and record.exc_info[1] is not None:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_text:
            payload["exception"] = record.exc_text
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", fmt: str = "text", log_dir: str | Path | None = None) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter: logging.Formatter
    if fmt == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.addFilter(RedactingFilter())
    root.addHandler(console)

    if log_dir:
        path = Path(log_dir)
        try:
            path.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(path / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.addFilter(RedactingFilter())
            root.addHandler(file_handler)
        except OSError:  # read-only FS etc. - console logging is enough
            pass

    for noisy in ("httpx", "httpcore", "urllib3", "sentence_transformers", "asyncio", "filelock", "docling", "docling_core", "docling_ibm_models", "huggingface_hub", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
