import re
import uuid

from services.lead_service import UPLOAD_DIR


def _post_lead(client, dummy_resume_path, **overrides):
    """Submit a multipart POST to /api/leads with sane defaults, allowing overrides."""
    data = {
        "firstName": "Jane",
        "lastName": "Doe",
        "email": "jane@example.com",
        **overrides.pop("data", {}),
    }
    content_type = overrides.pop("content_type", "application/pdf")
    with open(dummy_resume_path, "rb") as resume_file:
        files = {"resume": ("resume.pdf", resume_file.read(), content_type)}
    return client.post("/api/leads", data=data, files=files)


def test_create_lead_returns_201_with_expected_shape(client, dummy_resume_path):
    """A valid submission creates a PENDING lead and returns it as JSON."""
    response = _post_lead(client, dummy_resume_path)

    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["id"])
    assert body["firstName"] == "Jane"
    assert body["lastName"] == "Doe"
    assert body["email"] == "jane@example.com"
    assert body["state"] == "PENDING"
    assert body["resumeUrl"].startswith("http")
    assert "createdAt" in body
    assert "updatedAt" in body


def test_create_lead_stores_resume_file(client, dummy_resume_path):
    """The uploaded resume is written to UPLOAD_DIR under a timestamp_id.ext filename."""
    response = _post_lead(client, dummy_resume_path)

    body = response.json()
    filename = body["resumeUrl"].rsplit("/", 1)[-1]
    assert filename.endswith(f"{body['id']}.pdf")
    assert re.match(r"^\d{8}T\d{6}Z_", filename), f"expected a timestamp prefix, got {filename!r}"
    stored_file = UPLOAD_DIR / filename
    assert stored_file.exists()
    assert stored_file.read_bytes() == dummy_resume_path.read_bytes()


def test_create_lead_resume_url_is_fetchable(client, dummy_resume_path):
    """The returned resumeUrl actually serves the uploaded file's bytes."""
    response = _post_lead(client, dummy_resume_path)

    resume_url = response.json()["resumeUrl"]
    path = resume_url.split("testserver", 1)[-1] if "testserver" in resume_url else resume_url
    fetched = client.get(path if path.startswith("/") else resume_url)

    assert fetched.status_code == 200
    assert fetched.content == dummy_resume_path.read_bytes()


def test_create_lead_missing_first_name_returns_400(client, dummy_resume_path):
    """firstName is required."""
    with open(dummy_resume_path, "rb") as resume_file:
        files = {"resume": ("resume.pdf", resume_file.read(), "application/pdf")}
    response = client.post(
        "/api/leads",
        data={"lastName": "Doe", "email": "jane@example.com"},
        files=files,
    )

    assert response.status_code == 400


def test_create_lead_blank_first_name_returns_400(client, dummy_resume_path):
    """firstName cannot be whitespace-only."""
    response = _post_lead(client, dummy_resume_path, data={"firstName": "   "})

    assert response.status_code == 400


def test_create_lead_invalid_email_returns_400(client, dummy_resume_path):
    """email must be a validly formatted address."""
    response = _post_lead(client, dummy_resume_path, data={"email": "not-an-email"})

    assert response.status_code == 400


def test_create_lead_disallowed_file_type_returns_400(client, dummy_resume_path):
    """resume must be pdf/doc/docx."""
    response = _post_lead(client, dummy_resume_path, content_type="image/png")

    assert response.status_code == 400


def test_create_lead_oversized_content_length_returns_413(client):
    """A request whose Content-Length exceeds the limit is rejected before parsing."""
    oversized_bytes = b"0" * (7 * 1024 * 1024)
    files = {"resume": ("big.pdf", oversized_bytes, "application/pdf")}
    response = client.post(
        "/api/leads",
        data={"firstName": "Jane", "lastName": "Doe", "email": "jane@example.com"},
        files=files,
    )

    assert response.status_code == 413
