# Tactica AI Backend

Backend service for **Tactica AI**, an AI-powered academic planning platform that helps university students organize coursework, generate personalized study roadmaps, and interact with AI-powered academic assistants.

---

## Features

- 🔐 Authentication & Authorization
- 👤 User Management
- 📚 Course Management
- 📄 Document Upload & Processing
- 🤖 AI / RAG API
- 🧠 Embedding Generation
- 🔍 Vector Search
- 📅 Study Roadmap API
- 📆 Calendar Integration
- 🔔 Notification Service
- 📦 Background Job Processing

---

## Tech Stack

| Layer | Technology |
|--------|------------|
| Framework | FastAPI |
| Language | Python 3.12 |
| Database | PostgreSQL + pgvector |
| ORM | SQLAlchemy |
| AI | LangChain, LlamaIndex |
| LLM | Gemini / OpenAI |
| Authentication | Clerk |
| Background Jobs | Celery + Redis |
| Storage | Cloudflare R2 |
| Deployment | Railway |

---

## Project Structure

```
app/
├── api/              # API routes
├── core/             # Configuration & security
├── db/               # Database models & migrations
├── schemas/          # Pydantic schemas
├── services/         # Business logic
├── rag/              # RAG pipeline
├── workers/          # Celery tasks
├── utils/            # Utility functions
└── main.py           # FastAPI entry point

tests/
migrations/
scripts/
```

---

## Development Setup

### Clone repository

```bash
git clone git@github.com:<organization>/tactica_ai_backend.git
cd tactica-ai-backend
```

### Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment

```bash
cp .env.example .env
```

Fill in the required environment variables.

### Run locally

```bash
uvicorn app.main:app --reload
```

API will be available at

```
http://localhost:8000
```

Swagger documentation

```
http://localhost:8000/docs
```

---

## Application Logging

The backend uses centralized structured logging built on Python's standard `logging` library. Every log entry includes:

- UTC ISO 8601 timestamp with milliseconds
- log level
- request ID
- logger/module name
- message
- stack trace for exceptions

Example log lines:

```text
2026-07-13T10:30:45.123Z INFO [request_id=-] [module=app.main] Application started
2026-07-13T10:32:01.100Z INFO [request_id=req-001] [module=request] GET /health 200 18ms client_ip=127.0.0.1
```

### Logging Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Minimum level for console and application logs. |
| `LOG_DIR` | `logs` | Directory where log files are written. Created automatically. |
| `APP_LOG_FILE` | `app.log` | Application log filename inside `LOG_DIR`. |
| `ERROR_LOG_FILE` | `error.log` | Error log filename inside `LOG_DIR`. |
| `ENABLE_CONSOLE_LOG` | `true` | Enables or disables console logging. |

To change the log level or directory:

```bash
LOG_LEVEL=DEBUG LOG_DIR=/tmp/tactica-logs uvicorn app.main:app --reload
```

### Log Files

- `logs/app.log` contains `DEBUG`, `INFO`, and `WARNING` records only.
- `logs/error.log` contains `ERROR` and `CRITICAL` records only, including full exception tracebacks.

Generated `.log` files are ignored by git.

### Request IDs

Each incoming request receives a unique UUID request ID. The ID is:

- stored in async-safe request context for automatic log injection
- included in every log generated while handling the request
- returned to the client in the `X-Request-ID` response header

Use the response header to search related logs:

```bash
grep "request_id=<value-from-X-Request-ID>" logs/app.log logs/error.log
```

Inspect unexpected exceptions with:

```bash
tail -n 100 logs/error.log
```

Unexpected internal exceptions return a safe JSON response:

```json
{"detail": "Internal server error"}
```

Stack traces and internal exception details are never exposed to clients.

### Sensitive Data Rules

The request lifecycle middleware logs method, path, status code, duration, and client IP. It does not log request bodies, response bodies, authorization headers, cookies, tokens, or query values.

Logging sanitization redacts sensitive keys case-insensitively, including `password`, `password_hash`, `access_token`, `refresh_token`, `token`, `authorization`, `jwt_secret_key`, `database_password`, `db_password`, `secret`, and `api_key`. Nested dictionaries and collections are sanitized, and common strings such as `password=secret`, `"access_token": "secret"`, and `Authorization: Bearer secret` are written with `[REDACTED]`.

---

## Application Logging

The backend uses centralized structured logging built on Python's standard `logging` library. Every log entry includes:

- UTC ISO 8601 timestamp with milliseconds
- log level
- request ID
- logger/module name
- message
- stack trace for exceptions

Example log lines:

```text
2026-07-13T10:30:45.123Z INFO [request_id=-] [module=app.main] Application started
2026-07-13T10:32:01.100Z INFO [request_id=req-001] [module=request] GET /health 200 18ms client_ip=127.0.0.1
```

### Logging Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Minimum level for console and application logs. |
| `LOG_DIR` | `logs` | Directory where log files are written. Created automatically. |
| `APP_LOG_FILE` | `app.log` | Application log filename inside `LOG_DIR`. |
| `ERROR_LOG_FILE` | `error.log` | Error log filename inside `LOG_DIR`. |
| `ENABLE_CONSOLE_LOG` | `true` | Enables or disables console logging. |

To change the log level or directory:

```bash
LOG_LEVEL=DEBUG LOG_DIR=/tmp/tactica-logs uvicorn app.main:app --reload
```

### Log Files

- `logs/app.log` contains `DEBUG`, `INFO`, and `WARNING` records only.
- `logs/error.log` contains `ERROR` and `CRITICAL` records only, including full exception tracebacks.

Generated `.log` files are ignored by git.

### Request IDs

Each incoming request receives a unique UUID request ID. The ID is:

- stored in async-safe request context for automatic log injection
- included in every log generated while handling the request
- returned to the client in the `X-Request-ID` response header

Use the response header to search related logs:

```bash
grep "request_id=<value-from-X-Request-ID>" logs/app.log logs/error.log
```

Inspect unexpected exceptions with:

```bash
tail -n 100 logs/error.log
```

Unexpected internal exceptions return a safe JSON response:

```json
{"detail": "Internal server error"}
```

Stack traces and internal exception details are never exposed to clients.

### Sensitive Data Rules

The request lifecycle middleware logs method, path, status code, duration, and client IP. It does not log request bodies, response bodies, authorization headers, cookies, tokens, or query values.

Logging sanitization redacts sensitive keys case-insensitively, including `password`, `password_hash`, `access_token`, `refresh_token`, `token`, `authorization`, `jwt_secret_key`, `database_password`, `db_password`, `secret`, and `api_key`. Nested dictionaries and collections are sanitized, and common strings such as `password=secret`, `"access_token": "secret"`, and `Authorization: Bearer secret` are written with `[REDACTED]`.

---

## Local PostgreSQL Setup

The backend uses SQLAlchemy with PostgreSQL. Application startup executes
`SELECT 1` and stops with a safe error if the configured database is unavailable.
Database tables are not created during startup; Alembic will manage migrations.

### Prerequisites

- Python 3.12 virtual environment with `requirements.txt` installed
- Docker Desktop with the Docker daemon running

### Configure the environment

Create the local environment file:

```bash
cp .env.example .env
```

The example contains local-development placeholders only:

| Variable | Purpose |
|----------|---------|
| `DATABASE_HOST` | Safe host metadata used for connection logs (`localhost` on the host). |
| `DATABASE_PORT` | PostgreSQL port exposed by Docker Compose. |
| `DATABASE_NAME` | Database created by the PostgreSQL container. |
| `DATABASE_USER` | Local PostgreSQL user. |
| `DATABASE_PASSWORD` | Local PostgreSQL password; never log or commit it. |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection URL used by FastAPI. |

When FastAPI runs directly on the host, use `localhost` in `DATABASE_HOST` and
`DATABASE_URL`. If FastAPI later runs as a service inside Compose, use the Compose
service name `db` instead of `localhost`.

### Start and verify PostgreSQL

```bash
docker compose up -d
docker compose ps
docker compose logs db
```

Wait until the `db` service reports `healthy`, then start FastAPI:

```bash
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Stop PostgreSQL without deleting
its data with:

```bash
docker compose down
```

To stop PostgreSQL and permanently delete the local database volume:

```bash
docker compose down -v
```

Warning: `docker compose down -v` permanently deletes all data in the local
PostgreSQL volume.

### Troubleshooting

- **Docker daemon is not running:** Start Docker Desktop, wait for it to become
  ready, and rerun `docker compose up -d`.
- **Port 5432 is already in use:** Change `DATABASE_PORT` and the port in
  `DATABASE_URL` to the same available host port, then recreate the container.
- **Credentials changed in `.env`:** PostgreSQL initialization variables apply
  only when the data volume is first created. Restore the original credentials or
  recreate the local volume with `docker compose down -v`.
- **Stale PostgreSQL volume:** Run `docker compose down -v`, then
  `docker compose up -d`. This deletes existing local data.
- **Connection refused:** Confirm `docker compose ps` reports `db` as healthy and
  verify the host and port in `DATABASE_URL` match the way FastAPI is running.
- **`localhost` versus `db`:** Use `localhost` when FastAPI runs on your host. Use
  `db` only when FastAPI runs inside the same Compose network.

### Migrations

After Alembic configuration and migrations are added, apply migrations with:

```bash
alembic upgrade head
```

Create future migrations with:

```bash
alembic revision --autogenerate -m "your message"
```

---

## Git Workflow

This project follows Git Flow.

```
main
│
└── develop
      ├── feature/*
      └── bugfix/*
```

- **main** — Production
- **develop** — Integration
- **feature/*** — New features
- **bugfix/*** — Bug fixes

---

## Commit Convention

```
feat:
fix:
refactor:
docs:
test:
chore:
```

Example

```
feat(auth): implement JWT authentication
fix(api): resolve document upload validation
```

---

## API Documentation

Interactive API documentation is available after running the server.

- `/docs` — Swagger UI
- `/redoc` — ReDoc

---

## Related Repositories

- Frontend
- Infrastructure
- Documentation

---

## License

TBD
