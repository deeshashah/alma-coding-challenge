import uuid
from datetime import datetime, timedelta, timezone

from models import Lead, LeadState, User
from services.auth_service import create_access_token, hash_password


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


def _reset_leads(db_session):
    """Delete all existing Lead rows so total/ordering assertions aren't polluted by other tests."""
    db_session.query(Lead).delete()
    db_session.commit()


def _make_lead(db_session, *, created_at, state=LeadState.PENDING, **overrides):
    """Create and persist a test Lead with an explicit created_at for ordering control."""
    fields = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": f"{uuid.uuid4().hex}@example.com",
        "resume_url": "https://example.com/resumes/jane.pdf",
        "state": state,
        "created_at": created_at,
        **overrides,
    }
    lead = Lead(**fields)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


def test_list_leads_requires_auth(client):
    """GET /api/leads with no Authorization header returns 401."""
    response = client.get("/api/leads")
    assert response.status_code == 401


def test_get_lead_requires_auth(client):
    """GET /api/leads/:id with no Authorization header returns 401."""
    response = client.get(f"/api/leads/{uuid.uuid4()}")
    assert response.status_code == 401


def test_list_leads_returns_shape_and_ordering(client, db_session):
    """The list endpoint returns items/page/pageSize/total, most-recent-first."""
    headers = _auth_headers(db_session)
    _reset_leads(db_session)
    now = datetime.now(timezone.utc)
    older = _make_lead(db_session, created_at=now - timedelta(minutes=10))
    newer = _make_lead(db_session, created_at=now)

    response = client.get("/api/leads", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["pageSize"] == 20
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [str(newer.id), str(older.id)]


def test_list_leads_filters_by_state(client, db_session):
    """Passing ?state=REACHED_OUT only returns leads in that state."""
    headers = _auth_headers(db_session)
    _reset_leads(db_session)
    now = datetime.now(timezone.utc)
    pending = _make_lead(db_session, created_at=now, state=LeadState.PENDING)
    reached_out = _make_lead(
        db_session, created_at=now - timedelta(minutes=1), state=LeadState.REACHED_OUT
    )

    response = client.get("/api/leads", params={"state": "REACHED_OUT"}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(reached_out.id)]
    assert pending.id != reached_out.id


def test_list_leads_pagination(client, db_session):
    """Pagination slices results correctly and reports the true total."""
    headers = _auth_headers(db_session)
    _reset_leads(db_session)
    now = datetime.now(timezone.utc)
    leads = [
        _make_lead(db_session, created_at=now - timedelta(minutes=i)) for i in range(5)
    ]
    # leads[0] is most recent (created_at = now), leads[4] is oldest.

    page1 = client.get("/api/leads", params={"page": 1, "pageSize": 2}, headers=headers)
    page2 = client.get("/api/leads", params={"page": 2, "pageSize": 2}, headers=headers)
    page_out_of_range = client.get(
        "/api/leads", params={"page": 10, "pageSize": 2}, headers=headers
    )

    assert page1.status_code == page2.status_code == page_out_of_range.status_code == 200
    body1, body2, body3 = page1.json(), page2.json(), page_out_of_range.json()

    assert body1["total"] == body2["total"] == body3["total"] == 5
    assert [item["id"] for item in body1["items"]] == [str(leads[0].id), str(leads[1].id)]
    assert [item["id"] for item in body2["items"]] == [str(leads[2].id), str(leads[3].id)]
    assert body3["items"] == []


def test_get_lead_returns_matching_lead(client, db_session):
    """GET /api/leads/:id returns 200 with the correct lead for a known id."""
    headers = _auth_headers(db_session)
    lead = _make_lead(db_session, created_at=datetime.now(timezone.utc))

    response = client.get(f"/api/leads/{lead.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(lead.id)
    assert body["email"] == lead.email
    assert "updatedAt" in body


def test_get_lead_returns_404_for_unknown_id(client, db_session):
    """GET /api/leads/:id returns 404 for a nonexistent id."""
    headers = _auth_headers(db_session)

    response = client.get(f"/api/leads/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404
