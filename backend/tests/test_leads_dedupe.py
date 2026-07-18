"""HTTP-level test locking in that POST /api/leads never dedupes by email.

Each submission is treated as a distinct expression of interest — see
create_lead's docstring in lead_service.py for the reasoning.
"""

from models import Lead


def _post_lead(client, dummy_resume_path, **overrides):
    """Submit a multipart POST to /api/leads with sane defaults, allowing overrides."""
    data = {
        "firstName": "Jane",
        "lastName": "Doe",
        "email": "jane@example.com",
        **overrides.pop("data", {}),
    }
    with open(dummy_resume_path, "rb") as resume_file:
        files = {"resume": ("resume.pdf", resume_file.read(), "application/pdf")}
    return client.post("/api/leads", data=data, files=files)


def test_resubmission_same_email_creates_a_second_lead(client, dummy_resume_path, db_session):
    """Two submissions with the same email both return 201 and produce two distinct rows."""
    first = _post_lead(client, dummy_resume_path)
    second = _post_lead(client, dummy_resume_path, data={"firstName": "Janet"})

    assert first.status_code == 201
    assert second.status_code == 201

    first_body, second_body = first.json(), second.json()
    assert second_body["id"] != first_body["id"]
    assert db_session.query(Lead).filter(Lead.email == "jane@example.com").count() == 2
