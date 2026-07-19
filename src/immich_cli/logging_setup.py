"""Logging setup for immich-cli.

Provides a single ``configure_logging`` entry point used by the CLI to turn on
explicit tracing. Uses only the stdlib ``logging`` module — no extra deps.

Two opt-in flags (see ``cli.py``):

* ``--verbose``  — mirror logs to the console (stderr) at DEBUG.
* ``--log PATH`` — write the full DEBUG trace to ``PATH``.

Both may be used together. With neither set, the CLI logs nothing (only
Click's own error output reaches the user).

Security: the Immich API key is sent as the ``X-API-Key`` request header. The
HTTPX request hook redacts it before logging so secrets never land in a log
file.
"""

from __future__ import annotations

import logging
from datetime import datetime

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


def _format_time(record: logging.LogRecord, date_format: str = DATE_FORMAT) -> str:
    """Format the record time with microseconds.

    ``logging.Formatter`` uses ``time.strftime``, which does not understand
    ``%f`` (microseconds). We delegate to ``datetime.strftime`` instead so the
    high-resolution timestamp renders correctly.
    """
    return datetime.fromtimestamp(record.created).strftime(date_format)


def configure_logging(*, verbose: bool = False, log_file: str | None = None) -> None:
    """Configure the root ``immich_cli`` logger.

    Parameters
    ----------
    verbose:
        If True, also stream DEBUG logs to stderr (console).
    log_file:
        If set, write DEBUG logs to this file path.
    """
    if not verbose and not log_file:
        # Nothing requested: ensure the logger is effectively silent so the CLI
        # stays quiet by default.
        logging.getLogger("immich_cli").addHandler(logging.NullHandler())
        return

    logger = logging.getLogger("immich_cli")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    formatter.formatTime = _format_time

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if verbose:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
