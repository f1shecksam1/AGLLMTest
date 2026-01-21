import logging
import os
from logging.handlers import TimedRotatingFileHandler

import structlog
from structlog.contextvars import merge_contextvars

from app.core.config import settings


def configure_logging() -> None:
    os.makedirs(settings.log_dir, exist_ok=True)
    log_path = os.path.join(settings.log_dir, "app.log")

    # 1) stdlib root logger
    root = logging.getLogger()
    root.setLevel(settings.log_level)

    # 2) handlers
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

    # 3) structlog processors (ortak)
    pre_chain = [
        merge_contextvars,  # request_id vb.
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

    # 4) stdlib -> structlog formatter bridge
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

    # 5) structlog config
    structlog.configure(
        processors=pre_chain + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # (Opsiyonel) Uvicorn access loglarını kapatmak istersen:
    # logging.getLogger("uvicorn.access").disabled = True
