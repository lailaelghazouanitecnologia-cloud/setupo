import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from server.auth.middleware import LoginRequest, LoginResponse, verify_password, load_admin_token
from server.deps import require_user, require_admin, AuthContext
from server.routes.notifications import create_notification
from core import users
from core.errors import SetupoError

logger = logging.getLogger("setupo.auth")
router = APIRouter()


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class RegisterResponse(BaseModel):
    token: str
    email: str
    role: str
    user_id: str


class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    role: str
    balance: float
    verified: bool
    subdomain: Optional[str]
    created_at: str


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    try:
        user = await users.create_user(req.email, req.password, req.name)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)

    token = users.issue_token(user)
    display_name = user["name"]

    await create_notification(
        user["id"], "Welcome to NSO",
        f"Your account is ready, {display_name}. Deploy your first app or claim a free subdomain.",
        "success",
    )

    return RegisterResponse(token=token, email=user["email"], role=user["role"], user_id=user["id"])


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    admin = verify_password(req.email, req.password)
    if admin:
        token = load_admin_token()
        logger.info("Admin login: %s", req.email)
        return LoginResponse(token=token, email=req.email, role="admin")

    try:
        user = await users.authenticate(req.email, req.password)
    except SetupoError:
        raise HTTPException(401, "Invalid email or password")

    token = users.issue_token(user)
    return LoginResponse(token=token, email=user["email"], role=user["role"])


@router.get("/me", response_model=UserProfile)
async def get_me(auth: AuthContext = Depends(require_user)):
    try:
        user = await users.get_user(auth.user_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return UserProfile(**user)


@router.patch("/profile")
async def update_profile(req: UpdateProfileRequest, auth: AuthContext = Depends(require_user)):
    try:
        user = await users.update_profile(auth.user_id, name=req.name, email=req.email)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "user": user}


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, auth: AuthContext = Depends(require_user)):
    try:
        await users.change_password(auth.user_id, req.current_password, req.new_password)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.get("/users")
async def list_all_users(auth: AuthContext = Depends(require_admin)):
    all_users = await users.list_users()
    return {"users": all_users, "count": len(all_users)}
