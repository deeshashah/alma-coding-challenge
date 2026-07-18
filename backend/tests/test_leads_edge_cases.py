import uuid

from auth_service import create_access_token, hash_password
from models import User


def _make_user(db_session, *, email=None, password="correct-horse", name="Ada"):
    """Create and persist a test User with a properly hashed password."""
    if email is None:
        email = f"{uuid.uuid4().hex}@example.com"
    user = User(email=email, password_hash=hash_password(password), name=name)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_headers(db_session):
    """Create a User and return an Authorization header carrying a valid bearer token for it."""
    user = _make_user(db_session)
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def test_list_leads_invalid_state_filter_returns_400(client, db_session):
    """?state=BOGUS on GET /api/leads is rejected as 400, not silently ignored or 500."""
    headers = _auth_headers(db_session)

    response = client.get("/api/leads", params={"state": "BOGUS"}, headers=headers)

    assert response.status_code == 400


def test_list_leads_page_below_minimum_returns_400(client, db_session):
    """page=0 is out of the allowed range (>=1) and returns 400."""
    headers = _auth_headers(db_session)

    response = client.get("/api/leads", params={"page": 0}, headers=headers)

    assert response.status_code == 400


def test_list_leads_page_size_above_maximum_returns_400(client, db_session):
    """pageSize above the allowed maximum (100) returns 400 rather than serving an unbounded page."""
    headers = _auth_headers(db_session)

    response = client.get("/api/leads", params={"pageSize": 1000}, headers=headers)

    assert response.status_code == 400


def test_get_lead_malformed_uuid_returns_400(client, db_session):
    """A syntactically invalid id in the path is rejected as 400, not 500."""
    headers = _auth_headers(db_session)

    response = client.get("/api/leads/not-a-uuid", headers=headers)

    assert response.status_code == 400


def test_patch_lead_malformed_uuid_returns_400(client, db_session):
    """A syntactically invalid id in the PATCH path is rejected as 400, not 500."""
    headers = _auth_headers(db_session)

    response = client.patch(
        "/api/leads/not-a-uuid", json={"state": "REACHED_OUT"}, headers=headers
    )

    assert response.status_code == 400


def test_patch_lead_missing_state_field_returns_400(client, db_session):
    """A PATCH body without a state field is rejected as 400."""
    headers = _auth_headers(db_session)

    response = client.patch(
        f"/api/leads/{uuid.uuid4()}", json={}, headers=headers
    )

    assert response.status_code == 400


def test_patch_lead_invalid_state_value_returns_400(client, db_session):
    """A PATCH body with a state outside the LeadState enum is rejected as 400."""
    headers = _auth_headers(db_session)

    response = client.patch(
        f"/api/leads/{uuid.uuid4()}", json={"state": "BOGUS"}, headers=headers
    )

    assert response.status_code == 400


def test_list_leads_authorization_header_without_bearer_prefix_returns_401(client, db_session):
    """An Authorization header missing the 'Bearer ' prefix is treated as unauthenticated."""
    _make_user(db_session)

    response = client.get("/api/leads", headers={"Authorization": "just-a-token"})

    assert response.status_code == 401
