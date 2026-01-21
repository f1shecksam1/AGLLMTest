import logging
import os
from logging.handlers import TimedRotatingFileHandler

import structlog
from structlog.contextvars import merge_contextvars

from app.core.config import settings


def configure_logging() -> None:
    os.makedirs(settings.log_dir, exist_ok=True)
    log_path = os.path.join(settings.log_dir, "app.log")

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    sh = logging.StreamHandler()
    sh.setLevel(settings.log_level)

    fh = TimedRotatingFileHandler(
        filename=log_path,
        when="D",
        interval=1,
        backupCount=14,
        encoding="utf-8",
        utc=True,
    )
    fh.setLevel(settings.log_level)

    pre_chain = [
        merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer = structlog.dev.ConsoleRenderer(
        colors=False,
        pad_event=0,
        pad_level=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    sh.setFormatter(formatter)
    fh.setFormatter(formatter)

    root.handlers.clear()
    root.addHandler(sh)
    root.addHandler(fh)

    structlog.configure(
        processors=pre_chain + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger():
    return structlog.get_logger()
