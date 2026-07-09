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

## Database

This project uses:

- PostgreSQL
- pgvector for vector embeddings
- Alembic for database migrations

Run migrations

```bash
alembic upgrade head
```

Create a migration

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
