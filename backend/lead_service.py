import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from email_service import get_email_sender, send_with_retry
from models import Lead, LeadState

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(
    os.environ.get("UPLOAD_DIR", str(Path(__file__).resolve().parent / "uploads" / "resumes"))
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_ATTORNEY_NOTIFICATION_EMAIL = "attorney@example.com"


def create_lead(
    db: Session,
    *,
    lead_id: uuid.UUID,
    first_name: str,
    last_name: str,
    email: str,
    resume_bytes: bytes,
    filename: str,
    resume_url: str,
) -> Lead:
    """Persist an uploaded resume to disk and create the corresponding PENDING Lead row.

    Every submission creates a new lead, even if the email matches an existing one — each
    submission is treated as a distinct expression of interest (possibly with an updated
    resume), and an attorney should see that the person came back rather than have it
    silently merged into their prior lead.
    """
    file_path = UPLOAD_DIR / filename
    file_path.write_bytes(resume_bytes)

    lead = Lead(
        id=lead_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        resume_url=resume_url,
        state=LeadState.PENDING,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    return lead


class InvalidStateTransitionError(Exception):
    """Raised by update_lead_state when the requested target state is never a valid transition."""


class LeadStateConflictError(Exception):
    """Raised by update_lead_state when a concurrent request already changed the lead's state."""


def list_leads(
    db: Session,
    *,
    state: LeadState | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Lead], int]:
    """Return a (items, total_count) tuple of leads, most-recent-first, optionally filtered by state and paginated."""
    query = db.query(Lead)
    if state is not None:
        query = query.filter(Lead.state == state)

    total = query.count()
    items = (
        query.order_by(Lead.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_lead(db: Session, lead_id: uuid.UUID) -> Lead | None:
    """Fetch a single Lead by id, returning None if no such lead exists."""
    return db.query(Lead).filter(Lead.id == lead_id).first()


def update_lead_state(db: Session, lead_id: uuid.UUID, new_state: LeadState) -> Lead | None:
    """Transition a Lead's state via a single atomic conditional UPDATE, returning the updated Lead.

    Contract:
    - Returns None if no lead with lead_id exists at all (caller should respond 404).
    - Raises InvalidStateTransitionError if new_state isn't REACHED_OUT — that's never a
      valid target regardless of the lead's current state, so it's a plain bad request
      (caller should respond 400).
    - Raises LeadStateConflictError if the lead exists and new_state is REACHED_OUT, but
      the atomic UPDATE affected 0 rows because the lead's state wasn't PENDING at the
      moment the UPDATE ran — e.g. another request already transitioned it a moment ago.
      This is a race, not a bad request (caller should respond 409, not 400).

    Uses `UPDATE ... WHERE id = :id AND state = 'PENDING'` plus a rowcount check instead
    of a read-then-write, so two concurrent requests can't both pass a state check before
    either commits — only one UPDATE can ever affect the row. This holds even across
    multiple backend instances since it relies on DB-level atomicity, not an in-process
    lock.
    """
    if new_state != LeadState.REACHED_OUT:
        lead = get_lead(db, lead_id)
        if lead is None:
            return None
        raise InvalidStateTransitionError(
            f"Cannot transition lead from {lead.state} to {new_state}"
        )

    # This conditional update was added by me to take care of concurrent writes
    result = db.execute(
        update(Lead)
        .where(Lead.id == lead_id, Lead.state == LeadState.PENDING)
        .values(state=LeadState.REACHED_OUT, updated_at=datetime.now(timezone.utc))
    )

    if result.rowcount == 1:
        db.commit()
        return get_lead(db, lead_id)

    db.rollback()
    lead = get_lead(db, lead_id)
    if lead is None:
        return None
    raise LeadStateConflictError(
        f"Lead {lead_id} is no longer PENDING (current state: {lead.state})"
    )


def notify_lead_created(
    *,
    lead_id: uuid.UUID,
    first_name: str,
    last_name: str,
    email: str,
    resume_url: str,
) -> None:
    """Send confirmation/notification emails for a newly created lead, retrying transient failures.

    Meant to be scheduled via FastAPI BackgroundTasks (see leads.py's create_lead_route)
    rather than called on the request path, so a slow/down email provider never blocks
    lead creation. Takes plain scalar fields rather than a Lead ORM object because a
    background task runs after the request's DB session has already been closed —
    accessing an unloaded attribute on a detached ORM object at that point would raise
    DetachedInstanceError; plain values sidestep that entirely. Each send is retried with
    backoff (see email_service.send_with_retry); failures are logged there; this function
    never raises, since it must not (nothing awaits it or surfaces its errors otherwise).
    """
    sender = get_email_sender()

    send_with_retry(
        sender,
        to=email,
        subject="We've received your application",
        body=(
            f"Hi {first_name} {last_name},\n\n"
            "Thanks for submitting your information. Our team has received your "
            "application and will be in touch shortly.\n\n"
            "Best,\nThe Alma Team"
        ),
    )

    attorney_email = os.environ.get("ATTORNEY_NOTIFICATION_EMAIL")
    if not attorney_email:
        logger.warning(
            "ATTORNEY_NOTIFICATION_EMAIL is not set; falling back to default %s",
            DEFAULT_ATTORNEY_NOTIFICATION_EMAIL,
        )
        attorney_email = DEFAULT_ATTORNEY_NOTIFICATION_EMAIL

    send_with_retry(
        sender,
        to=attorney_email,
        subject=f"New lead: {first_name} {last_name}",
        body=(
            f"A new lead has been submitted by {first_name} {last_name} "
            f"({email}).\n\nResume: {resume_url}\nLead ID: {lead_id}"
        ),
    )
