import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from models import Lead, LeadState

VALID_LEAD_FIELDS = {
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane@example.com",
    "resume_url": "https://example.com/resumes/jane.pdf",
}


def test_lead_defaults_to_pending_state(db_session):
    """A new Lead defaults to PENDING state and gets an id/timestamps automatically."""
    lead = Lead(**VALID_LEAD_FIELDS)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    assert lead.state == LeadState.PENDING
    assert isinstance(lead.id, uuid.UUID)
    assert lead.created_at is not None
    assert lead.updated_at is not None


def test_lead_state_transitions_to_reached_out(db_session):
    """A Lead's state can be moved from PENDING to REACHED_OUT."""
    lead = Lead(**VALID_LEAD_FIELDS)
    db_session.add(lead)
    db_session.commit()

    lead.state = LeadState.REACHED_OUT
    db_session.commit()
    db_session.refresh(lead)

    assert lead.state == LeadState.REACHED_OUT


def test_lead_updated_at_changes_on_mutation(db_session):
    """updated_at advances when a Lead is mutated and re-committed."""
    lead = Lead(**VALID_LEAD_FIELDS)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    first_updated_at = lead.updated_at

    lead.state = LeadState.REACHED_OUT
    db_session.commit()
    db_session.refresh(lead)

    assert lead.updated_at >= first_updated_at


@pytest.mark.parametrize("missing_field", sorted(VALID_LEAD_FIELDS))
def test_lead_required_field_cannot_be_null(db_session, missing_field):
    """firstName, lastName, email, and resumeUrl are all required (NOT NULL)."""
    fields = {**VALID_LEAD_FIELDS, missing_field: None}
    lead = Lead(**fields)
    db_session.add(lead)

    with pytest.raises(IntegrityError):
        db_session.commit()
