from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.session import validate_database_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_database_connection()
    yield


app = FastAPI(
    title="Tactica AI Backend",
    description="Backend API for Tactica AI",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
def root():
    return {"message": "Welcome to Tactica AI Backend"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
