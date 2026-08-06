from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from core.auth import authenticate_user, change_user_password, get_user_by_identity

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    identity: str
    password: str


class ChangePasswordRequest(BaseModel):
    user_identity: str
    current_password: str
    new_password: str


@router.post("/login")
def login_endpoint(payload: LoginRequest):
    if not payload.identity.strip() or not payload.password.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email/username and password are required."
        )
    user = authenticate_user(payload.identity, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or user not found."
        )
    return {"status": "success", "user": user}


@router.get("/me")
def get_me_endpoint(user_identity: str):
    user = get_user_by_identity(user_identity)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User session not found."
        )
    return {"status": "success", "user": user}


@router.post("/change-password")
def change_password_endpoint(payload: ChangePasswordRequest):
    ok, msg = change_user_password(
        payload.user_identity,
        payload.current_password,
        payload.new_password
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {"status": "success", "message": msg}
