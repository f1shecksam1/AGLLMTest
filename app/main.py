import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.logging import configure_logging, get_logger
from app.api.v1.routers.health import router as health_router
from app.api.v1.routers.llm import router as llm_router

log = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("app.start")
    yield
    log.info("app.stop")


app = FastAPI(title="hardware-metrics-llm", lifespan=lifespan)
app.include_router(health_router, prefix="/api/v1")
app.include_router(llm_router, prefix="/api/v1")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start = time.perf_counter()

    clear_contextvars()
    bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=str(request.url.path),
        query=str(request.url.query),
        client_ip=request.client.host if request.client else None,
    )

    log.info("http.request.received")

    try:
        response: Response = await call_next(request)
        return response
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log.info(
            "http.response.sent",
            status_code=getattr(locals().get("response", None), "status_code", None),
            duration_ms=duration_ms,
        )
        clear_contextvars()
