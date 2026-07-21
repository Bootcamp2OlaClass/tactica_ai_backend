from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.session import validate_database_connection
from app.routers import auth
from app.routers import test


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

#Routers
app.include_router(auth.router)
app.include_router(test.router)


@app.get("/")
def root():
    return {"message": "Welcome to Tactica AI Backend"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
