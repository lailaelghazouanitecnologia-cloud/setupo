import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from nso.shared.auth.resolve import LoginRequest, LoginResponse, verify_password, load_admin_token
from nso.shared.deps import require_user, require_admin, AuthContext
from nso.engine.notifications.routes import create_notification
from nso.engine.auth import service as users
from nso.engine.notifications import service as email_service
from nso.shared.errors import NsoError

logger = logging.getLogger("nso.auth")
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


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    try:
        user = await users.create_user(req.email, req.password, req.name)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)

    token = users.issue_token(user)
    display_name = user["name"]

    await create_notification(
        user["id"], "Welcome to NSO",
        f"Your account is ready, {display_name}. Deploy your first app or claim a free subdomain.",
        "success",
    )

    # Send verification email (non-blocking)
    try:
        await email_service.send_verification_email(user["id"], user["email"])
    except Exception as e:
        logger.warning("Verification email failed for %s: %s", user["email"], e)

    return RegisterResponse(token=token, email=user["email"], role=user["role"], user_id=user["id"])


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    admin = verify_password(req.email, req.password)
    if admin:
        # Ensure admin user exists in DB so user-scoped endpoints work
        user = await users.get_user_by_email(req.email)
        if not user:
            user = await users.create_user(req.email, req.password, "Admin")
            from nso.shared import db as _db
            await _db.update("users", user["id"], {"role": "admin", "verified": 1})
            user["role"] = "admin"
        elif user.get("role") != "admin":
            from nso.shared import db as _db
            await _db.update("users", user["id"], {"role": "admin"})
            user["role"] = "admin"
        token = users.issue_token(user)
        logger.info("Admin login: %s", req.email)
        return LoginResponse(token=token, email=req.email, role="admin")

    try:
        user = await users.authenticate(req.email, req.password)
    except NsoError:
        raise HTTPException(401, "Invalid email or password")

    token = users.issue_token(user)
    return LoginResponse(token=token, email=user["email"], role=user["role"])


@router.get("/me", response_model=UserProfile)
async def get_me(auth: AuthContext = Depends(require_user)):
    try:
        user = await users.get_user(auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return UserProfile(**user)


@router.patch("/profile")
async def update_profile(req: UpdateProfileRequest, auth: AuthContext = Depends(require_user)):
    try:
        user = await users.update_profile(auth.user_id, name=req.name, email=req.email)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "user": user}


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, auth: AuthContext = Depends(require_user)):
    try:
        await users.change_password(auth.user_id, req.current_password, req.new_password)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.get("/users")
async def list_all_users(auth: AuthContext = Depends(require_admin)):
    all_users = await users.list_users()
    return {"users": all_users, "count": len(all_users)}


# ── Email verification ────────────────────────────────────────

@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest):
    """Verify email address using token from verification email."""
    try:
        user_id = await email_service.confirm_verification(req.token)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)

    user = await users.get_user(user_id)

    # Send welcome email
    try:
        await email_service.send_welcome(user["email"], user["name"])
    except Exception as e:
        logger.warning("Welcome email failed for %s: %s", user["email"], e)

    return {"ok": True, "user_id": user_id, "email": user["email"]}


@router.post("/resend-verification")
async def resend_verification(req: ResendVerificationRequest):
    """Resend verification email. Silent if email not found (security)."""
    user = await users.get_user_by_email(req.email)
    if user and not user.get("verified"):
        try:
            await email_service.send_verification_email(user["id"], user["email"])
        except Exception as e:
            logger.warning("Resend verification failed for %s: %s", req.email, e)
    # Always return ok (don't reveal if email exists)
    return {"ok": True, "message": "If the email exists, a verification link has been sent."}


# ── Password reset ────────────────────────────────────────────

@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """Send password reset email. Silent if email not found (security)."""
    try:
        await email_service.send_reset_email(req.email)
    except Exception as e:
        logger.warning("Reset email failed for %s: %s", req.email, e)
    return {"ok": True, "message": "If the email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """Reset password using token from reset email."""
    try:
        user_id = await email_service.confirm_reset(req.token, req.new_password)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "user_id": user_id}
