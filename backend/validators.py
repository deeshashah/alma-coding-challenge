from fastapi import HTTPException, UploadFile

MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# Content-Length covers the whole multipart body (other fields + boundaries),
# not just the resume part, so allow some headroom over the file limit itself.
MAX_REQUEST_SIZE_BYTES = MAX_RESUME_SIZE_BYTES + 1024 * 1024  # 6 MB

ALLOWED_RESUME_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


def validate_content_length(content_length: str | None) -> None:
    """Raise 413 if a request's Content-Length header exceeds MAX_REQUEST_SIZE_BYTES.

    Meant to run before the request body is read/parsed, so an oversized
    upload can be rejected without buffering it. Silently passes through
    when the header is absent (e.g. chunked transfer encoding) — callers
    should still enforce the limit after reading via validate_resume_size.
    """
    if content_length is None:
        return
    if int(content_length) > MAX_REQUEST_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="request body too large")


def validate_required_text(value: str, field_name: str) -> str:
    """Raise 400 if value is empty/whitespace-only; otherwise return it unchanged."""
    if not value or not value.strip():
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    return value


def validate_resume_type(resume: UploadFile) -> str:
    """Raise 400 if resume's content type isn't pdf/doc/docx; otherwise return its file extension."""
    extension = ALLOWED_RESUME_TYPES.get(resume.content_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="resume must be one of: pdf, doc, docx")
    return extension


def validate_resume_size(contents: bytes) -> bytes:
    """Raise 400 if resume is empty or exceeds MAX_RESUME_SIZE_BYTES; otherwise return it unchanged."""
    if not contents:
        raise HTTPException(status_code=400, detail="resume file is empty")
    if len(contents) > MAX_RESUME_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="resume file exceeds 5MB limit")
    return contents
