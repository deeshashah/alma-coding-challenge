import uuid

from models import User
from services.auth_service import hash_password


def _make_user(db_session, *, email=None, password="correct-horse", name="Ada"):
    """Create and persist a test User with a properly hashed password.

    Emails default to a random unique address so repeated test runs never collide
    on the users.email unique constraint even if the sqlite file isn't reset between runs.
    """
    if email is None:
        email = f"{uuid.uuid4().hex}@example.com"
    user = User(email=email, password_hash=hash_password(password), name=name)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_login_success_returns_token_and_user(client, db_session):
    """Correct credentials return 200 with a token and the user's public fields."""
    user = _make_user(db_session, password="right-pass", name="Ada Lovelace")

    response = client.post(
        "/api/auth/login", json={"email": user.email, "password": "right-pass"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["email"] == user.email
    assert body["user"]["name"] == "Ada Lovelace"


def test_login_response_never_includes_password_hash(client, db_session):
    """The password_hash must never leak into the login response body."""
    user = _make_user(db_session, password="right-pass")

    response = client.post(
        "/api/auth/login", json={"email": user.email, "password": "right-pass"}
    )

    assert response.status_code == 200
    assert "password_hash" not in response.text
    assert "passwordHash" not in response.text


def test_login_wrong_password_returns_401(client, db_session):
    """An incorrect password returns 401."""
    user = _make_user(db_session, password="right-pass")

    response = client.post(
        "/api/auth/login", json={"email": user.email, "password": "nope"}
    )

    assert response.status_code == 401


def test_login_unknown_email_returns_401(client, db_session):
    """A login attempt for an email with no matching user returns 401."""
    response = client.post(
        "/api/auth/login", json={"email": f"{uuid.uuid4().hex}@example.com", "password": "whatever"}
    )

    assert response.status_code == 401


def test_login_missing_fields_returns_error(client):
    """A malformed body (missing password) returns a client error, not a 500."""
    response = client.post("/api/auth/login", json={"email": "someone@example.com"})

    assert response.status_code in (400, 422)


def test_login_invalid_email_format_returns_error(client):
    """A non-email-shaped email field returns a client error, not a 500."""
    response = client.post(
        "/api/auth/login", json={"email": "not-an-email", "password": "whatever"}
    )

    assert response.status_code in (400, 422)


def test_health_endpoint_still_unauthenticated(client):
    """GET /api/health remains public and unaffected by the new auth router."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
