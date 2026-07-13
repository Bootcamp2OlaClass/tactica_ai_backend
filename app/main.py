from fastapi import FastAPI

app = FastAPI(
    title="Tactica AI Backend",
    description="Backend API for Tactica AI",
    version="0.1.0",
)


@app.get("/")
def root():
    return {"message": "Welcome to Tactica AI Backend"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}