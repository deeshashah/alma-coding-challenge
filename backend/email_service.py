"""Email-sending abstraction used to notify prospects and attorneys about lead activity.

Provides an `EmailSender` interface with three implementations: `ConsoleEmailSender`
(default, logs instead of sending — safe for local dev), `SMTPEmailSender` (a minimal
stdlib-only real sender), and `ResendEmailSender` (a minimal stdlib-only client for the
Resend HTTP API — no SDK dependency). `get_email_sender()` is the factory callers should
use; it picks the implementation based on the `EMAIL_BACKEND` env var.

`send_with_retry()` wraps any EmailSender with retry-with-backoff and guaranteed failure
logging, since a background send failure would otherwise be silent — the caller (see
lead_service.notify_lead_created, invoked via FastAPI BackgroundTasks so a slow/down
provider never blocks lead creation) should use this rather than calling sender.send()
directly.
"""

import json
import logging
import os
import smtplib
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from email.message import EmailMessage

logger = logging.getLogger(__name__)
# uvicorn only configures its own uvicorn.* loggers, not the root logger — it
# never calls logging.basicConfig(). With no handler on root, Python falls
# back to logging.lastResort, a WARNING-only stderr handler, so raising just
# this logger's level to INFO isn't enough; the fallback handler still drops
# it. Attach a dedicated handler so ConsoleEmailSender's output actually shows
# up locally regardless of how the app is launched. propagate=False avoids
# double-printing if something else configures the root logger later.
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 1.0


class EmailSender(ABC):
    """Interface for sending a single plain-text email."""

    @abstractmethod
    def send(self, *, to: str, subject: str, body: str) -> None:
        """Send an email to `to` with the given `subject` and `body`, raising on failure."""
        raise NotImplementedError


class ConsoleEmailSender(EmailSender):
    """Logs the email instead of actually sending it. Default backend for local dev."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        """Log the email's contents at INFO level instead of delivering it."""
        logger.info("Email to=%s subject=%r body=%r", to, subject, body)


class SMTPEmailSender(EmailSender):
    """Sends real email via SMTP using only the stdlib (smtplib + email.message)."""

    def __init__(
        self,
        *,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        from_address: str | None = None,
    ) -> None:
        """Store SMTP connection settings used by send()."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_address = from_address or username or "no-reply@example.com"

    def send(self, *, to: str, subject: str, body: str) -> None:
        """Send an email via SMTP (STARTTLS if supported). Raises on any failure."""
        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self.host, self.port) as smtp:
            smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


class ResendEmailSender(EmailSender):
    """Sends real email via the Resend HTTP API using only the stdlib (urllib), no SDK."""

    API_URL = "https://api.resend.com/emails"

    def __init__(self, *, api_key: str, from_address: str) -> None:
        """Store the Resend API key and from-address used by send()."""
        self.api_key = api_key
        self.from_address = from_address

    def send(self, *, to: str, subject: str, body: str) -> None:
        """POST to the Resend API, raising on any non-2xx response or network error."""
        payload = json.dumps(
            {"from": self.from_address, "to": [to], "subject": subject, "text": body}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.API_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # urllib's default User-Agent ("Python-urllib/x.y") trips
                # Cloudflare's bot protection in front of Resend's API
                # (blocked with a 403 before the request reaches Resend at all).
                "User-Agent": "alma-challenge-backend/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10):
                pass
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Resend API returned {exc.code}: {detail}") from exc


def get_email_sender() -> EmailSender:
    """Return the configured EmailSender implementation based on the EMAIL_BACKEND env var.

    Defaults to ConsoleEmailSender ("console"). Set EMAIL_BACKEND=smtp for SMTPEmailSender
    (configured via SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_ADDRESS)
    or EMAIL_BACKEND=resend for ResendEmailSender (configured via RESEND_API_KEY and
    RESEND_FROM_ADDRESS) — the real-provider path SYSTEM_DESIGN.md calls for.
    """
    backend = os.environ.get("EMAIL_BACKEND", "console").strip().lower()
    if backend == "smtp":
        return SMTPEmailSender(
            host=os.environ.get("SMTP_HOST", ""),
            port=int(os.environ.get("SMTP_PORT", "587")),
            username=os.environ.get("SMTP_USERNAME"),
            password=os.environ.get("SMTP_PASSWORD"),
            from_address=os.environ.get("SMTP_FROM_ADDRESS"),
        )
    if backend == "resend":
        return ResendEmailSender(
            api_key=os.environ.get("RESEND_API_KEY", ""),
            from_address=os.environ.get("RESEND_FROM_ADDRESS", "no-reply@example.com"),
        )
    return ConsoleEmailSender()


def send_with_retry(
    sender: EmailSender,
    *,
    to: str,
    subject: str,
    body: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
) -> bool:
    """Attempt sender.send() up to max_attempts times with exponential backoff between tries.

    Runs to completion in-process (via time.sleep for the backoff) rather than returning
    a pending future — callers that don't want this to block should schedule it via
    FastAPI BackgroundTasks rather than calling it inline on the request path, since sync
    background tasks already run in a threadpool and a blocking sleep there doesn't stall
    the event loop.

    A background send failure is otherwise silent — no exception ever reaches an HTTP
    response, so nothing would surface the error anywhere. Logs a warning per failed
    attempt and, only once every attempt has been exhausted, an error-level "gave up" log
    so a failed notification is at least discoverable in server logs. Returns True if the
    email was sent (on any attempt), False if every attempt failed.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            sender.send(to=to, subject=subject, body=body)
            return True
        except Exception:
            is_last_attempt = attempt == max_attempts
            log = logger.error if is_last_attempt else logger.warning
            log(
                "Email send attempt %d/%d to=%s subject=%r failed%s",
                attempt,
                max_attempts,
                to,
                subject,
                "; giving up" if is_last_attempt else "; retrying",
                exc_info=True,
            )
            if not is_last_attempt:
                time.sleep(base_delay_seconds * (2 ** (attempt - 1)))
    return False
