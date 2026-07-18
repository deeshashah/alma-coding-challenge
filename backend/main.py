from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # must run before importing modules that read env vars at import time (e.g. database.py)

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from auth import router as auth_router
from auth_service import seed_attorney_from_env
from database import Base, SessionLocal, engine
from lead_service import UPLOAD_DIR
from leads import router as leads_router
from models import Lead, User  # noqa: F401 — registers Lead/User on Base.metadata
from validators import validate_content_length


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables and seed an attorney account (if configured) on startup."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_attorney_from_env(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Alma Challenge API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    """Reject an oversized POST /api/leads body via Content-Length before it's parsed."""
    if request.method == "POST" and request.url.path == "/api/leads":
        try:
            validate_content_length(request.headers.get("content-length"))
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return 400 (per SYSTEM_DESIGN.md) instead of FastAPI's default 422 for validation errors."""
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


app.include_router(leads_router)
app.include_router(auth_router)
app.mount("/uploads/resumes", StaticFiles(directory=str(UPLOAD_DIR)), name="resumes")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Report basic liveness of the API."""
    return {"status": "ok"}
