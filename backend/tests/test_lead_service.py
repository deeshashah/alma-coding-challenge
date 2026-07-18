import uuid

from models import LeadState


def test_create_lead_writes_file_and_persists_row(app, db_session, dummy_resume_path):
    """create_lead() writes the resume to UPLOAD_DIR and inserts a matching PENDING row."""
    from services.lead_service import UPLOAD_DIR, create_lead

    lead_id = uuid.uuid4()
    filename = f"{lead_id}.pdf"
    resume_bytes = dummy_resume_path.read_bytes()

    lead = create_lead(
        db_session,
        lead_id=lead_id,
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        resume_bytes=resume_bytes,
        filename=filename,
        resume_url=f"https://example.com/uploads/resumes/{filename}",
    )

    assert lead.id == lead_id
    assert lead.state == LeadState.PENDING
    assert (UPLOAD_DIR / filename).read_bytes() == resume_bytes
