import os
import tempfile
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Set at import time (module level), not inside a fixture. Pytest imports
# every test module during collection, before ANY fixture — including
# session-scoped ones — ever runs. A test file with a module-level
# `from models import ...` (e.g. test_lead_model.py) transitively imports
# database.py, which reads DATABASE_URL and creates `engine` as soon as it's
# imported. If that happened before a fixture got a chance to override the
# env vars, `engine` would stay bound to the real dev alma.db for the whole
# session. conftest.py is guaranteed to load before test collection in its
# directory, so setting these here — not via tmp_path_factory, which isn't
# available outside a fixture — is what actually guarantees isolation.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="alma-test-db-"))
_TEST_UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="alma-test-uploads-"))

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_DIR / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_TEST_UPLOAD_DIR)
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-production"


@pytest.fixture(scope="session")
def app():
    """Import the FastAPI app against the test database/upload dir and ensure tables exist."""
    from database import Base, engine
    from main import app as fastapi_app

    Base.metadata.create_all(bind=engine)
    return fastapi_app


@pytest.fixture()
def client(app):
    """Yield a TestClient, running the app's startup/shutdown lifespan."""
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(app):
    """Yield a raw SQLAlchemy session bound to the test database."""
    from database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def dummy_resume_path() -> Path:
    """Path to a minimal placeholder PDF used to exercise the resume upload path."""
    return FIXTURES_DIR / "dummy_resume.pdf"


@pytest.fixture(autouse=True)
def _reset_tables(app):
    """Clear all rows after each test so row-count/pagination assertions aren't order-dependent.

    The test database is created once per session (see the `app` fixture), so
    without this, Lead/User rows created by one test would still be present
    when a later test runs and counts/paginates over the same tables.
    """
    yield
    from database import SessionLocal
    from models import Lead, User

    session = SessionLocal()
    try:
        session.query(Lead).delete()
        session.query(User).delete()
        session.commit()
    finally:
        session.close()
