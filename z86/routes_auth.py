"""
z86 auth routes — register, login, profile.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from z86 import users

router = APIRouter(prefix="/auth")


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/register")
async def register(req: RegisterRequest):
    user = await users.create_user(req.email, req.password, req.name)
    token = users.issue_token(user)
    return {"token": token, "user": user}


@router.post("/login")
async def login(req: LoginRequest):
    user = await users.authenticate(req.email, req.password)
    token = users.issue_token(user)
    return {"token": token, "user": user}


@router.get("/me")
async def me(user=Depends(users.require_user)):
    return user


@router.patch("/profile")
async def update_profile(req: UpdateProfileRequest, user=Depends(users.require_user)):
    updated = await users.update_profile(user["id"], req.name, req.email)
    return updated


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, user=Depends(users.require_user)):
    await users.change_password(user["id"], req.current_password, req.new_password)
    return {"ok": True}
