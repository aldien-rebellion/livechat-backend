from fastapi import APIRouter
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    return {
        "access_token": "sample_access_token",
        "refresh_token": "sample_refresh_token",
        "token_type": "bearer"
    }

@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest):
    return {
        "access_token": "new_sample_access_token",
        "refresh_token": "new_sample_refresh_token",
        "token_type": "bearer"
    }