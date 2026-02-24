"""Auth Routes — Login endpoint for dashboard."""
import logging

from fastapi import APIRouter, HTTPException

from server.auth.middleware import LoginRequest, LoginResponse, verify_password, load_admin_token

logger = logging.getLogger("setupo.auth")
router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate with email/password for dashboard access. Returns admin token."""
    user = verify_password(req.email, req.password)
    if not user:
        logger.warning("Failed login attempt for %s", req.email)
        raise HTTPException(401, "Invalid email or password")

    token = load_admin_token()
    logger.info("Successful login for %s", req.email)
    return LoginResponse(token=token, email=req.email, role=user["role"])
