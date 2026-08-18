from contextlib import asynccontextmanager
import logging
import time
from uuid import uuid4

import redis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import (
    configure_logging,
    reset_request_id,
    set_request_id,
)
from app.db.session import validate_database_connection
from app.routers import auth
from app.routers import calendar
from app.routers import chat
from app.routers import courses
from app.routers import dashboard
from app.routers import degree
from app.routers import documents
from app.routers import extraction
from app.routers import notification
from app.routers import rag
from app.routers import recovery_plan
from app.routers import roadmap
from app.routers import task
from app.routers import semester


configure_logging()

logger = logging.getLogger(__name__)
request_logger = logging.getLogger("request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[STARTUP] Application starting")

    if settings.llm_provider is None:
        # Deliberately not fail-fast: every non-AI endpoint (auth, courses,
        # tasks, documents, calendar) works with zero LLM configuration, so
        # refusing to boot here would take down unrelated features over a
        # missing key. Logged at startup instead of only surfacing the first
        # time a student hits /api/v1/chat/stream and gets a 503, so an
        # operator can catch a misconfigured deployment from the boot logs.
        logger.warning(
            "LLM_PROVIDER is not set -- AI features (chat, document "
            "extraction, embeddings) are disabled. Set LLM_PROVIDER="
            "gemini|openai|groq plus the matching *_API_KEY to enable them."
        )

    try:
        logger.info("[STARTUP] Connecting to PostgreSQL...")
        validate_database_connection()
        logger.info("[STARTUP] Database connection successful")
        logger.info("[STARTUP] FastAPI ready to accept requests")
        yield
    finally:
        logger.info("[STARTUP] Application shutdown")


app = FastAPI(
    title="Tactica AI Backend",
    description="Backend API for Tactica AI",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Routers
app.include_router(auth.router)
app.include_router(calendar.router)
app.include_router(chat.router)
app.include_router(courses.router)
app.include_router(dashboard.router)
app.include_router(degree.router)
app.include_router(documents.router)
app.include_router(extraction.router)
app.include_router(notification.router)
app.include_router(rag.router)
app.include_router(recovery_plan.router)
app.include_router(roadmap.router)
app.include_router(task.router)
app.include_router(semester.router)


@app.middleware("http")
async def request_logging_middleware(
    request: Request,
    call_next,
):
    request_id = str(uuid4())
    token = set_request_id(request_id)
    start_time = time.perf_counter()

    try:
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round(
                (time.perf_counter() - start_time) * 1000
            )
            client_ip = (
                request.client.host
                if request.client
                else "unknown"
            )

            request_logger.exception(
                "%s %s 500 %sms client_ip=%s",
                request.method,
                request.url.path,
                duration_ms,
                client_ip,
            )

            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
            # This middleware sits outside CORSMiddleware in the stack (it's
            # registered via the @app.middleware("http") decorator, which
            # always wraps middleware added through app.add_middleware --
            # see main.py's registration order above). CORSMiddleware never
            # gets a chance to stamp its headers onto a response fabricated
            # here, so an unhandled exception on any endpoint came back to
            # the browser with no Access-Control-Allow-Origin header at all.
            # A browser reports that as a CORS failure, not a 500 -- which
            # sent debugging a real backend crash (found via the dashboard
            # endpoint) off toward "CORS is misconfigured" instead. Mirror
            # CORSMiddleware's own origin check here so the true 500 (and
            # its request ID) reaches the browser's network tab instead of
            # being masked.
            origin = request.headers.get("origin")
            if origin and origin in settings.cors_allowed_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            duration_ms = round(
                (time.perf_counter() - start_time) * 1000
            )
            client_ip = (
                request.client.host
                if request.client
                else "unknown"
            )

            request_logger.info(
                "%s %s %s %sms client_ip=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                client_ip,
            )

        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        reset_request_id(token)


@app.get("/")
def root():
    return {"message": "Welcome to Tactica AI Backend"}


@app.get("/health")
def health_check():
    redis_status = "unreachable"
    try:
        client = redis.from_url(
            settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        if client.ping():
            redis_status = "connected"
    except Exception:
        redis_status = "unreachable"

    return {"status": "healthy", "redis": redis_status}
