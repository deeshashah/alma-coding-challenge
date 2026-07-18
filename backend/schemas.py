import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models import LeadState


class LeadOut(BaseModel):
    """Serialized representation of a Lead returned by the API (camelCase JSON)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    email: str
    resume_url: str = Field(alias="resumeUrl")
    state: LeadState
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class LoginRequest(BaseModel):
    """Request body for POST /api/auth/login."""

    email: EmailStr
    password: str


class UserOut(BaseModel):
    """Serialized representation of a User (attorney), excluding password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str


class LoginResponse(BaseModel):
    """Response body for POST /api/auth/login."""

    token: str
    user: UserOut


class LeadListOut(BaseModel):
    """Response body for GET /api/leads: a page of leads plus pagination metadata."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[LeadOut]
    page: int
    page_size: int = Field(alias="pageSize")
    total: int


class LeadStateUpdate(BaseModel):
    """Request body for PATCH /api/leads/:id."""

    state: LeadState
