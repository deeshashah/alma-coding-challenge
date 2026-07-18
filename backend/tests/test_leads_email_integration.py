"""Integration test: creating a lead via POST /api/leads triggers confirmation/notification emails."""

import services.lead_service as lead_service


class _RecordingEmailSender:
    """Fake EmailSender that records every send() call instead of delivering anything."""

    def __init__(self):
        """Start with an empty call log."""
        self.calls = []

    def send(self, *, to, subject, body):
        """Record the call's arguments instead of sending an email."""
        self.calls.append({"to": to, "subject": subject, "body": body})


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


def test_create_lead_sends_confirmation_and_attorney_emails(client, dummy_resume_path, monkeypatch):
    """A successful lead creation sends one email to the prospect and one to the attorney."""
    fake_sender = _RecordingEmailSender()
    monkeypatch.setattr(lead_service, "get_email_sender", lambda: fake_sender)
    monkeypatch.setenv("ATTORNEY_NOTIFICATION_EMAIL", "counsel@example.com")

    response = _post_lead(client, dummy_resume_path)

    assert response.status_code == 201
    assert len(fake_sender.calls) == 2

    recipients = {call["to"] for call in fake_sender.calls}
    assert recipients == {"jane@example.com", "counsel@example.com"}

    prospect_call = next(call for call in fake_sender.calls if call["to"] == "jane@example.com")
    attorney_call = next(call for call in fake_sender.calls if call["to"] == "counsel@example.com")

    assert "received" in prospect_call["subject"].lower()
    assert "Jane" in attorney_call["subject"]
    assert "Jane" in attorney_call["body"]
    assert "jane@example.com" in attorney_call["body"]


def test_create_lead_falls_back_to_default_attorney_email(client, dummy_resume_path, monkeypatch):
    """When ATTORNEY_NOTIFICATION_EMAIL is unset, the notification falls back to the default address."""
    fake_sender = _RecordingEmailSender()
    monkeypatch.setattr(lead_service, "get_email_sender", lambda: fake_sender)
    monkeypatch.delenv("ATTORNEY_NOTIFICATION_EMAIL", raising=False)

    response = _post_lead(client, dummy_resume_path, data={"email": "john@example.com"})

    assert response.status_code == 201
    recipients = {call["to"] for call in fake_sender.calls}
    assert recipients == {"john@example.com", lead_service.DEFAULT_ATTORNEY_NOTIFICATION_EMAIL}


def test_create_lead_succeeds_even_when_email_sending_fails(client, dummy_resume_path, monkeypatch):
    """A failing email backend does not prevent the lead from being created successfully."""
    import services.email_service as email_service

    class _ExplodingSender:
        """Fake EmailSender whose send() always raises, simulating a delivery failure."""

        def send(self, *, to, subject, body):
            """Always fail, as if the email provider were unreachable."""
            raise RuntimeError("email provider unavailable")

    monkeypatch.setattr(lead_service, "get_email_sender", lambda: _ExplodingSender())
    # send_with_retry sleeps between attempts (exponential backoff) — every
    # attempt fails here, so without this the test would burn several real
    # seconds per run. The retry *count* is still exercised, just not the wait.
    monkeypatch.setattr(email_service.time, "sleep", lambda _seconds: None)

    response = _post_lead(client, dummy_resume_path, data={"email": "resilient@example.com"})

    assert response.status_code == 201
    assert response.json()["email"] == "resilient@example.com"
