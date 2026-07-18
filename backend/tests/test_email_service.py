"""Unit tests for email_service: senders, get_email_sender(), and send_with_retry()."""

import logging
import urllib.error

import pytest

from services.email_service import (
    ConsoleEmailSender,
    ResendEmailSender,
    SMTPEmailSender,
    get_email_sender,
    send_with_retry,
)


def test_console_email_sender_logs_email_contents(caplog):
    """ConsoleEmailSender.send() logs the recipient, subject, and body instead of sending."""
    sender = ConsoleEmailSender()

    with caplog.at_level(logging.INFO, logger="services.email_service"):
        sender.send(to="prospect@example.com", subject="Hello", body="Welcome aboard.")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "prospect@example.com" in record.getMessage()
    assert "Hello" in record.getMessage()
    assert "Welcome aboard." in record.getMessage()


def test_get_email_sender_defaults_to_console(monkeypatch):
    """With EMAIL_BACKEND unset, get_email_sender() returns a ConsoleEmailSender."""
    monkeypatch.delenv("EMAIL_BACKEND", raising=False)

    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_get_email_sender_explicit_console(monkeypatch):
    """EMAIL_BACKEND=console returns a ConsoleEmailSender."""
    monkeypatch.setenv("EMAIL_BACKEND", "console")

    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_get_email_sender_smtp_reads_env_vars(monkeypatch):
    """EMAIL_BACKEND=smtp returns an SMTPEmailSender configured from SMTP_* env vars."""
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_ADDRESS", "noreply@example.com")

    sender = get_email_sender()

    assert isinstance(sender, SMTPEmailSender)
    assert sender.host == "smtp.example.com"
    assert sender.port == 2525
    assert sender.username == "user@example.com"
    assert sender.password == "secret"
    assert sender.from_address == "noreply@example.com"


def test_get_email_sender_smtp_defaults_port_and_from_address(monkeypatch):
    """SMTP_PORT defaults to 587 and from_address falls back to username when unset."""
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.delenv("SMTP_FROM_ADDRESS", raising=False)

    sender = get_email_sender()

    assert sender.port == 587
    assert sender.from_address == "user@example.com"


class _FakeSMTP:
    """Records the SMTP calls made against it, standing in for smtplib.SMTP in tests."""

    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port):
        """Record the host/port used to construct this fake SMTP connection."""
        self.host = host
        self.port = port
        self.starttls_called = False
        self.login_args = None
        self.sent_messages = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        """Support use as a context manager, like the real smtplib.SMTP."""
        return self

    def __exit__(self, *exc_info):
        """No-op cleanup on context exit."""
        return False

    def starttls(self):
        """Record that STARTTLS was requested."""
        self.starttls_called = True

    def login(self, username, password):
        """Record the credentials used to authenticate."""
        self.login_args = (username, password)

    def send_message(self, message):
        """Record the EmailMessage that was sent."""
        self.sent_messages.append(message)


def test_smtp_email_sender_send_uses_smtplib(monkeypatch):
    """SMTPEmailSender.send() opens an SMTP connection, does STARTTLS/login, and sends the message."""
    _FakeSMTP.instances = []
    monkeypatch.setattr("services.email_service.smtplib.SMTP", _FakeSMTP)

    sender = SMTPEmailSender(
        host="smtp.example.com",
        port=2525,
        username="user@example.com",
        password="secret",
        from_address="noreply@example.com",
    )
    sender.send(to="someone@example.com", subject="Subject", body="Body text")

    assert len(_FakeSMTP.instances) == 1
    fake = _FakeSMTP.instances[0]
    assert fake.host == "smtp.example.com"
    assert fake.port == 2525
    assert fake.starttls_called is True
    assert fake.login_args == ("user@example.com", "secret")
    assert len(fake.sent_messages) == 1
    sent = fake.sent_messages[0]
    assert sent["To"] == "someone@example.com"
    assert sent["Subject"] == "Subject"
    assert sent["From"] == "noreply@example.com"


def test_smtp_email_sender_send_propagates_errors(monkeypatch):
    """SMTPEmailSender.send() lets smtplib errors raise — callers are responsible for catching them."""

    class _ExplodingSMTP(_FakeSMTP):
        def starttls(self):
            """Simulate an SMTP failure when attempting STARTTLS."""
            raise OSError("connection refused")

    monkeypatch.setattr("services.email_service.smtplib.SMTP", _ExplodingSMTP)

    sender = SMTPEmailSender(host="smtp.example.com")

    with pytest.raises(OSError):
        sender.send(to="someone@example.com", subject="Subject", body="Body")


def test_get_email_sender_resend_reads_env_vars(monkeypatch):
    """EMAIL_BACKEND=resend returns a ResendEmailSender configured from RESEND_* env vars."""
    monkeypatch.setenv("EMAIL_BACKEND", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_ADDRESS", "noreply@example.com")

    sender = get_email_sender()

    assert isinstance(sender, ResendEmailSender)
    assert sender.api_key == "re_test_key"
    assert sender.from_address == "noreply@example.com"


class _FakeHTTPResponse:
    """Minimal stand-in for the context-manager object urllib.request.urlopen returns."""

    def __enter__(self):
        """Support use as a context manager."""
        return self

    def __exit__(self, *exc_info):
        """No-op cleanup on context exit."""
        return False


def test_resend_email_sender_send_posts_expected_payload(monkeypatch):
    """ResendEmailSender.send() POSTs a JSON payload with the Resend API key and message fields."""
    captured = {}

    def _fake_urlopen(request, timeout):
        """Record the outgoing urllib.request.Request instead of hitting the network."""
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        captured["body"] = request.data
        captured["timeout"] = timeout
        return _FakeHTTPResponse()

    monkeypatch.setattr("services.email_service.urllib.request.urlopen", _fake_urlopen)

    sender = ResendEmailSender(api_key="re_test_key", from_address="noreply@example.com")
    sender.send(to="someone@example.com", subject="Subject", body="Body text")

    assert captured["url"] == ResendEmailSender.API_URL
    assert captured["method"] == "POST"
    assert captured["headers"]["authorization"] == "Bearer re_test_key"
    assert captured["headers"]["content-type"] == "application/json"
    # urllib's default User-Agent ("Python-urllib/x.y") gets blocked by
    # Cloudflare's bot protection in front of the real Resend API with a 403
    # before the request ever reaches Resend's own logic — regression test
    # for that: a custom User-Agent must always be sent.
    assert captured["headers"]["user-agent"] == "alma-challenge-backend/1.0"

    import json

    payload = json.loads(captured["body"])
    assert payload == {
        "from": "noreply@example.com",
        "to": ["someone@example.com"],
        "subject": "Subject",
        "text": "Body text",
    }


def test_resend_email_sender_send_raises_on_http_error(monkeypatch):
    """ResendEmailSender.send() raises when the Resend API returns a non-2xx response."""

    def _fake_urlopen(request, timeout):
        """Simulate an HTTP error response from the Resend API."""
        raise urllib.error.HTTPError(
            ResendEmailSender.API_URL, 401, "Unauthorized", {}, None
        )

    monkeypatch.setattr("services.email_service.urllib.request.urlopen", _fake_urlopen)

    sender = ResendEmailSender(api_key="bad_key", from_address="noreply@example.com")

    with pytest.raises(RuntimeError, match="401"):
        sender.send(to="someone@example.com", subject="Subject", body="Body")


class _CountingSender:
    """Fake EmailSender that fails a fixed number of times before succeeding, or always fails."""

    def __init__(self, fail_times):
        """Track how many more times send() should raise before succeeding."""
        self.fail_times = fail_times
        self.attempts = 0

    def send(self, *, to, subject, body):
        """Raise until fail_times is exhausted, then succeed."""
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise RuntimeError(f"attempt {self.attempts} failed")


def test_send_with_retry_succeeds_on_first_attempt(monkeypatch):
    """send_with_retry returns True and doesn't sleep when the first attempt succeeds."""
    monkeypatch.setattr("services.email_service.time.sleep", lambda _seconds: pytest.fail("should not sleep"))
    sender = _CountingSender(fail_times=0)

    result = send_with_retry(sender, to="x@example.com", subject="s", body="b")

    assert result is True
    assert sender.attempts == 1


def test_send_with_retry_succeeds_after_transient_failures(monkeypatch):
    """send_with_retry retries on failure and returns True once a later attempt succeeds."""
    sleeps = []
    monkeypatch.setattr("services.email_service.time.sleep", lambda seconds: sleeps.append(seconds))
    sender = _CountingSender(fail_times=2)

    result = send_with_retry(
        sender, to="x@example.com", subject="s", body="b", max_attempts=3
    )

    assert result is True
    assert sender.attempts == 3
    assert len(sleeps) == 2  # backoff between attempts 1->2 and 2->3, none after the final success
    assert sleeps == sorted(sleeps)  # exponential backoff: non-decreasing


def test_send_with_retry_gives_up_after_max_attempts(monkeypatch, caplog):
    """send_with_retry returns False and logs a final error once every attempt is exhausted."""
    monkeypatch.setattr("services.email_service.time.sleep", lambda _seconds: None)
    sender = _CountingSender(fail_times=99)

    with caplog.at_level(logging.WARNING, logger="services.email_service"):
        result = send_with_retry(
            sender, to="x@example.com", subject="s", body="b", max_attempts=3
        )

    assert result is False
    assert sender.attempts == 3
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert "giving up" in error_records[0].getMessage()
