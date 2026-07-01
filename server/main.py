"""FastAPI application bootstrap for the Portfolio Compressor service."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from server.config import OUTPUT_DIR, UPLOAD_DIR
from server.jobs import JobManager
from server.ratelimit import limiter
from server.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create and tear down shared application state."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app.state.job_manager = JobManager()
    try:
        yield
    finally:
        app.state.job_manager.clear()


app = FastAPI(title="Portfolio Compressor MVP", lifespan=lifespan)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(router)


@app.get("/")
def healthcheck() -> dict[str, str]:
    """Return a simple health response for local verification."""
    return {"status": "ok", "service": "portfolio-compressor"}


if __name__ == "__main__":
    uvicorn.run("server.main:app", host="127.0.0.1", port=8000, reload=True)
