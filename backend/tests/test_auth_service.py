import uuid

import pytest
from fastapi import HTTPException

from models import User
from services.auth_service import (
    authenticate_attorney,
    create_access_token,
    decode_access_token,
    get_current_attorney,
    hash_password,
    seed_attorney_from_env,
    verify_password,
)


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


def test_hash_password_does_not_return_plaintext():
    """The stored hash must never equal the original password."""
    password = "super-secret"
    hashed = hash_password(password)

    assert hashed != password
    assert isinstance(hashed, str)
    assert len(hashed) > 0


def test_verify_password_accepts_correct_and_rejects_wrong():
    """verify_password should accept the right password and reject an incorrect one."""
    hashed = hash_password("correct-password")

    assert verify_password("correct-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_create_and_decode_access_token_round_trip():
    """A token created for a user id should decode back to the same user id."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id)

    decoded_id = decode_access_token(token)

    assert decoded_id == user_id


def test_decode_access_token_rejects_garbage():
    """A malformed token should raise HTTPException(401)."""
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not-a-real-token")

    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_expired_token(monkeypatch):
    """An expired token should raise HTTPException(401)."""
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "-1")
    user_id = uuid.uuid4()
    token = create_access_token(user_id)

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)

    assert exc_info.value.status_code == 401


def test_authenticate_attorney_success(db_session):
    """authenticate_attorney returns the User when email and password both match."""
    user = _make_user(db_session, password="right-pass")

    result = authenticate_attorney(db_session, user.email, "right-pass")

    assert result is not None
    assert result.id == user.id


def test_authenticate_attorney_wrong_password(db_session):
    """authenticate_attorney returns None when the password doesn't match."""
    user = _make_user(db_session, password="right-pass")

    result = authenticate_attorney(db_session, user.email, "wrong-pass")

    assert result is None


def test_authenticate_attorney_unknown_email(db_session):
    """authenticate_attorney returns None when no user has that email."""
    result = authenticate_attorney(db_session, "nobody@example.com", "whatever")

    assert result is None


def test_get_current_attorney_with_valid_token(db_session):
    """get_current_attorney resolves the User for a valid bearer token."""
    user = _make_user(db_session)
    token = create_access_token(user.id)

    result = get_current_attorney(authorization=f"Bearer {token}", db=db_session)

    assert result.id == user.id


def test_get_current_attorney_missing_header(db_session):
    """get_current_attorney raises 401 when no Authorization header is present."""
    with pytest.raises(HTTPException) as exc_info:
        get_current_attorney(authorization=None, db=db_session)

    assert exc_info.value.status_code == 401


def test_get_current_attorney_garbage_token(db_session):
    """get_current_attorney raises 401 for a malformed bearer token."""
    with pytest.raises(HTTPException) as exc_info:
        get_current_attorney(authorization="Bearer garbage-token", db=db_session)

    assert exc_info.value.status_code == 401


def test_get_current_attorney_missing_bearer_prefix(db_session):
    """get_current_attorney raises 401 when the header lacks the 'Bearer ' prefix."""
    user = _make_user(db_session)
    token = create_access_token(user.id)

    with pytest.raises(HTTPException) as exc_info:
        get_current_attorney(authorization=token, db=db_session)

    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_wrong_signing_secret(db_session, monkeypatch):
    """A well-formed JWT signed with a different secret is rejected, not just malformed ones."""
    import datetime

    import jwt

    user = _make_user(db_session)
    now = datetime.datetime.now(datetime.timezone.utc)
    forged_token = jwt.encode(
        {"sub": str(user.id), "iat": now, "exp": now + datetime.timedelta(minutes=5)},
        "a-completely-different-secret-nobody-configured",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(forged_token)

    assert exc_info.value.status_code == 401


def test_get_current_attorney_expired_token(db_session, monkeypatch):
    """get_current_attorney raises 401 for an expired token."""
    user = _make_user(db_session)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "-1")
    token = create_access_token(user.id)

    with pytest.raises(HTTPException) as exc_info:
        get_current_attorney(authorization=f"Bearer {token}", db=db_session)

    assert exc_info.value.status_code == 401


def test_get_current_attorney_user_no_longer_exists(db_session):
    """get_current_attorney raises 401 if the token's user id has no matching row."""
    token = create_access_token(uuid.uuid4())

    with pytest.raises(HTTPException) as exc_info:
        get_current_attorney(authorization=f"Bearer {token}", db=db_session)

    assert exc_info.value.status_code == 401


def test_seed_attorney_from_env_creates_user(db_session, monkeypatch):
    """seed_attorney_from_env creates a User when all three env vars are set."""
    monkeypatch.setenv("SEED_ATTORNEY_EMAIL", "seed@example.com")
    monkeypatch.setenv("SEED_ATTORNEY_PASSWORD", "seed-pass")
    monkeypatch.setenv("SEED_ATTORNEY_NAME", "Seeded Attorney")

    seed_attorney_from_env(db_session)

    user = db_session.query(User).filter(User.email == "seed@example.com").first()
    assert user is not None
    assert user.name == "Seeded Attorney"
    assert verify_password("seed-pass", user.password_hash)


def test_seed_attorney_from_env_is_idempotent(db_session, monkeypatch):
    """Calling seed_attorney_from_env twice should not create a duplicate user."""
    monkeypatch.setenv("SEED_ATTORNEY_EMAIL", "seed2@example.com")
    monkeypatch.setenv("SEED_ATTORNEY_PASSWORD", "seed-pass")
    monkeypatch.setenv("SEED_ATTORNEY_NAME", "Seeded Attorney")

    seed_attorney_from_env(db_session)
    seed_attorney_from_env(db_session)

    users = db_session.query(User).filter(User.email == "seed2@example.com").all()
    assert len(users) == 1


def test_seed_attorney_from_env_noop_when_vars_missing(db_session, monkeypatch):
    """seed_attorney_from_env does nothing if any of the three env vars are unset."""
    monkeypatch.delenv("SEED_ATTORNEY_EMAIL", raising=False)
    monkeypatch.delenv("SEED_ATTORNEY_PASSWORD", raising=False)
    monkeypatch.delenv("SEED_ATTORNEY_NAME", raising=False)

    seed_attorney_from_env(db_session)  # should not raise

    count_before = db_session.query(User).count()
    seed_attorney_from_env(db_session)
    count_after = db_session.query(User).count()
    assert count_before == count_after
