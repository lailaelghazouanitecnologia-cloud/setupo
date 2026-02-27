import logging
import re
import secrets as stdlib_secrets

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from server.auth.middleware import LoginRequest, LoginResponse, verify_password, load_admin_token
from server.auth.jwt import hash_password, verify_password as verify_user_password, create_user_token
from server.deps import require_user, AuthContext
from server.routes.notifications import create_notification
from core import db

logger = logging.getLogger("setupo.auth")
router = APIRouter()

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
MIN_PASSWORD_LENGTH = 6


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
    created_at: str


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    email = req.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Invalid email format")
    if len(req.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    existing = await db.fetch_one("users", email=email)
    if existing:
        raise HTTPException(409, "Email already registered")

    user_id = f"user_{stdlib_secrets.token_hex(12)}"
    pw_hash = hash_password(req.password)
    display_name = req.name.strip() or email.split("@")[0]

    await db.insert("users", {
        "id": user_id,
        "email": email,
        "password_hash": pw_hash,
        "name": display_name,
        "role": "user",
        "balance": 0.00,
        "verified": 0,
    })

    token = create_user_token(user_id, email, "user")
    logger.info("New user registered: %s (%s)", email, user_id)

    await create_notification(
        user_id, "Welcome to NSO",
        f"Your account is ready, {display_name}. Deploy your first app or claim a free subdomain.",
        "success",
    )

    return RegisterResponse(token=token, email=email, role="user", user_id=user_id)


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    admin = verify_password(req.email, req.password)
    if admin:
        token = load_admin_token()
        logger.info("Admin login: %s", req.email)
        return LoginResponse(token=token, email=req.email, role="admin")

    email = req.email.strip().lower()
    user = await db.fetch_one("users", email=email)
    if not user or not verify_user_password(req.password, user["password_hash"]):
        logger.warning("Failed login attempt for %s", req.email)
        raise HTTPException(401, "Invalid email or password")

    token = create_user_token(user["id"], user["email"], user["role"])
    logger.info("User login: %s (%s)", user["email"], user["id"])
    return LoginResponse(token=token, email=user["email"], role=user["role"])


@router.get("/me")
async def get_me(auth: AuthContext = Depends(require_user)):
    user = await db.fetch_one("users", id=auth.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return UserProfile(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        role=user["role"],
        balance=user["balance"],
        verified=user["verified"],
        created_at=user["created_at"],
    )
