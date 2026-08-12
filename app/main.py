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
from app.routers import courses
from app.routers import dashboard
from app.routers import documents
from app.routers import test
from app.routers import rbac_test
from app.routers import task
from app.routers import semester


configure_logging()

logger = logging.getLogger(__name__)
request_logger = logging.getLogger("request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application started")

    try:
        validate_database_connection()
        yield
    finally:
        logger.info("Application shutdown")


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
app.include_router(courses.router)
app.include_router(dashboard.router)
app.include_router(documents.router)
app.include_router(test.router)
app.include_router(rbac_test.router)
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
    # Redis/worker availability is reported here for operator visibility but
    # deliberately does NOT affect this endpoint's status or status code —
    # background-job infrastructure is optional for the app to be "up";
    # synchronous CRUD works with no worker running at all. See
    # PHASE_04_BACKGROUND_JOBS.md "Health checks" for the reasoning.
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
