import uuid
from datetime import datetime, timezone

from auth_service import create_access_token, hash_password
from models import Lead, LeadState, User


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


def _make_lead(db_session, *, state=LeadState.PENDING, **overrides):
    """Create and persist a test Lead."""
    fields = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": f"{uuid.uuid4().hex}@example.com",
        "resume_url": "https://example.com/resumes/jane.pdf",
        "state": state,
        **overrides,
    }
    lead = Lead(**fields)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


def test_patch_lead_requires_auth(client):
    """PATCH /api/leads/:id with no Authorization header returns 401."""
    response = client.patch(f"/api/leads/{uuid.uuid4()}", json={"state": "REACHED_OUT"})
    assert response.status_code == 401


def test_patch_lead_transitions_pending_to_reached_out(client, db_session):
    """A PENDING lead transitions to REACHED_OUT and updatedAt advances."""
    headers = _auth_headers(db_session)
    lead = _make_lead(db_session, state=LeadState.PENDING)
    original_updated_at = lead.updated_at

    response = client.patch(
        f"/api/leads/{lead.id}", json={"state": "REACHED_OUT"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "REACHED_OUT"
    assert datetime.fromisoformat(body["updatedAt"].replace("Z", "+00:00")) >= original_updated_at


def test_patch_lead_already_reached_out_returns_409(client, db_session):
    """Re-transitioning an already-REACHED_OUT lead is a conflict (409), not a bad request.

    Distinguishing this from test_patch_lead_to_pending_returns_400 matters: this is the
    exact scenario two attorneys racing on the same lead would hit (both see PENDING,
    only one atomic UPDATE wins), so the frontend needs a distinct status to tell
    "someone already handled this" apart from a generically malformed request.
    """
    headers = _auth_headers(db_session)
    lead = _make_lead(db_session, state=LeadState.REACHED_OUT)

    response = client.patch(
        f"/api/leads/{lead.id}", json={"state": "REACHED_OUT"}, headers=headers
    )

    assert response.status_code == 409


def test_patch_lead_second_request_after_transition_returns_409(client, db_session):
    """A second PATCH against a lead already transitioned by a prior request gets 409.

    Unlike test_patch_lead_already_reached_out_returns_409 (which starts from a lead
    that's REACHED_OUT from the moment it's created), this drives the SAME atomic UPDATE
    code path through both the winning and losing outcome sequentially — the closest a
    single-threaded TestClient can get to exercising the exact two-attorneys-race scenario
    the TODO in SYSTEM_DESIGN.md describes, without needing real thread-level concurrency.
    """
    headers = _auth_headers(db_session)
    lead = _make_lead(db_session, state=LeadState.PENDING)

    responses = [
        client.patch(f"/api/leads/{lead.id}", json={"state": "REACHED_OUT"}, headers=headers)
        for _ in range(2)
    ]
    statuses = sorted(r.status_code for r in responses)

    assert statuses == [200, 409]


def test_patch_lead_to_pending_returns_400(client, db_session):
    """Attempting to set state back to PENDING returns 400."""
    headers = _auth_headers(db_session)
    lead = _make_lead(db_session, state=LeadState.PENDING)

    response = client.patch(f"/api/leads/{lead.id}", json={"state": "PENDING"}, headers=headers)

    assert response.status_code == 400


def test_patch_lead_returns_404_for_unknown_id(client, db_session):
    """PATCH /api/leads/:id returns 404 for a nonexistent id."""
    headers = _auth_headers(db_session)

    response = client.patch(
        f"/api/leads/{uuid.uuid4()}", json={"state": "REACHED_OUT"}, headers=headers
    )

    assert response.status_code == 404
