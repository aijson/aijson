import logging
import os

import structlog
from structlog_sentry import SentryProcessor


_configured = False


def configure_logging(pretty=True, additional_processors=None, level=None):
    if additional_processors is None:
        additional_processors = []

    if level is None:
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--log-level",
            default="WARNING",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        )
        args, _ = parser.parse_known_args()
        level = getattr(logging, args.log_level)

    logging.basicConfig(
        level=level,
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )

    library_log_level = max(level, logging.INFO)

    # silence the boto3 logs a bit
    logging.getLogger("openai").setLevel(library_log_level)
    # logging.getLogger("httpx").setLevel(logging.INFO)
    # logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("boto3").setLevel(library_log_level)
    logging.getLogger("aioboto3").setLevel(library_log_level)
    logging.getLogger("botocore").setLevel(library_log_level)
    logging.getLogger("aiobotocore").setLevel(library_log_level)

    processors = additional_processors + [
        structlog.stdlib.add_log_level,  # add log level
    ]

    if "SENTRY_DSN" in os.environ:
        processors += [
            SentryProcessor(event_level=logging.ERROR),
        ]
    if pretty:
        processors += [
            structlog.dev.set_exc_info,  # add exception info
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        processors += [
            structlog.processors.format_exc_info,  # add exception info
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        cache_logger_on_first_use=True,
    )

    global _configured
    _configured = True


def get_logger(*args, **kwargs) -> structlog.stdlib.BoundLogger:
    # Configure logging on first logger use, if not configured yet
    if not _configured:
        configure_logging()

    log = structlog.get_logger(*args, **kwargs)
    return log
