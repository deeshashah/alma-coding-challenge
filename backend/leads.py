import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import EmailStr
from sqlalchemy.orm import Session

from auth_service import get_current_attorney
from database import get_db
from lead_service import (
    InvalidStateTransitionError,
    LeadStateConflictError,
    create_lead,
    get_lead,
    list_leads,
    notify_lead_created,
    update_lead_state,
)
from models import Lead, LeadState, User
from schemas import LeadListOut, LeadOut, LeadStateUpdate
from validators import validate_required_text, validate_resume_size, validate_resume_type

router = APIRouter()


@router.post("/api/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead_route(
    request: Request,
    background_tasks: BackgroundTasks,
    first_name: str = Form(..., alias="firstName"),
    last_name: str = Form(..., alias="lastName"),
    email: EmailStr = Form(...),
    resume: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Lead:
    """Handle POST /api/leads: validate the request, delegate persistence, queue email notifications.

    Every submission creates a new lead — see create_lead's docstring for why a matching
    email doesn't merge into an existing row.
    """
    first_name = validate_required_text(first_name, "firstName")
    last_name = validate_required_text(last_name, "lastName")
    extension = validate_resume_type(resume)
    resume_bytes = validate_resume_size(await resume.read())

    lead_id = uuid.uuid4()
    # Timestamp prefix is for on-disk traceability/sortability, not collision
    # avoidance — lead_id is already a fresh UUID per submission, so different
    # leads can't collide regardless. It's defense-in-depth against a future
    # change away from random UUIDs (e.g. sequential ids), which would
    # otherwise reintroduce a real overwrite risk for uploads close in time.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}_{lead_id}{extension}"
    resume_url = str(request.url_for("resumes", path=filename))

    lead = create_lead(
        db,
        lead_id=lead_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        resume_bytes=resume_bytes,
        filename=filename,
        resume_url=resume_url,
    )

    # Scheduled via BackgroundTasks (runs after the response is sent) rather than
    # awaited here, so a slow/down email provider never blocks lead creation.
    # Plain fields, not the ORM object — see notify_lead_created's docstring.
    background_tasks.add_task(
        notify_lead_created,
        lead_id=lead.id,
        first_name=lead.first_name,
        last_name=lead.last_name,
        email=lead.email,
        resume_url=lead.resume_url,
    )

    return lead


@router.get("/api/leads", response_model=LeadListOut)
def list_leads_route(
    state: LeadState | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_attorney),
) -> LeadListOut:
    """Handle GET /api/leads: list leads most-recent-first, optionally filtered and paginated."""
    items, total = list_leads(db, state=state, page=page, page_size=page_size)
    return LeadListOut(items=items, page=page, page_size=page_size, total=total)


@router.get("/api/leads/{lead_id}", response_model=LeadOut)
def get_lead_route(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_attorney),
) -> Lead:
    """Handle GET /api/leads/:id: fetch a single lead, or 404 if it doesn't exist."""
    lead = get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    return lead


@router.patch("/api/leads/{lead_id}", response_model=LeadOut)
def update_lead_state_route(
    lead_id: uuid.UUID,
    body: LeadStateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_attorney),
) -> Lead:
    """Handle PATCH /api/leads/:id: apply a state transition, or 404/400/409 on failure."""
    try:
        lead = update_lead_state(db, lead_id, body.state)
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LeadStateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    return lead
