from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from schemas import LoginRequest, LoginResponse
from services.auth_service import authenticate_attorney, create_access_token

router = APIRouter()


@router.post("/api/auth/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Handle POST /api/auth/login: authenticate credentials and issue a bearer token."""
    user = authenticate_attorney(db, request.email, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    token = create_access_token(user.id)
    return LoginResponse(token=token, user=user)
