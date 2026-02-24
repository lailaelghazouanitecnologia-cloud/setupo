"""MMS Auth Routes - Login endpoint."""
import logging

from fastapi import APIRouter, HTTPException

from server.auth import LoginRequest, LoginResponse, verify_password, load_token

logger = logging.getLogger("mms.auth")

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate with email and password, returns API token."""
    user = verify_password(req.email, req.password)
    if not user:
        logger.warning("Failed login attempt for %s", req.email)
        raise HTTPException(401, "Invalid email or password")

    token = load_token()
    logger.info("Successful login for %s", req.email)
    return LoginResponse(token=token, email=req.email, role=user["role"])
