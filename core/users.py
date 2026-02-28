import logging
import re
import secrets

import aiosqlite

from core import db
from core.errors import ConflictError, NotFoundError, ValidationError, AuthError
from server.auth.jwt import hash_password, verify_password, create_user_token

logger = logging.getLogger("setupo.users")

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
SUBDOMAIN_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")

MIN_PASSWORD_LENGTH = 6
MAX_NAME_LENGTH = 64
MAX_EMAIL_LENGTH = 254

RESERVED_SUBDOMAINS = frozenset({
    "www", "api", "admin", "app", "mail", "ftp", "ns1", "ns2",
    "agent", "dashboard", "status", "docs", "blog", "help",
    "support", "dev", "staging", "test", "nso", "cdn", "assets",
    "static", "media", "images", "auth", "login", "register",
    "billing", "pay", "webhook", "webhooks", "ws", "wss",
})

USER_FIELDS = (
    "id", "email", "name", "role", "balance",
    "verified", "subdomain", "last_active", "created_at",
)


def _sanitize_user(row: dict) -> dict:
    return {k: row[k] for k in USER_FIELDS if k in row}


def _validate_email(email: str) -> str:
    email = email.strip().lower()
    if not email or len(email) > MAX_EMAIL_LENGTH:
        raise ValidationError("Invalid email address")
    if not EMAIL_RE.match(email):
        raise ValidationError("Invalid email format")
    return email


def _validate_password(password: str):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def _validate_name(name: str) -> str:
    name = name.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"Name must be under {MAX_NAME_LENGTH} characters")
    return name


def _validate_subdomain(sub: str) -> str:
    sub = sub.strip().lower()
    if not SUBDOMAIN_RE.match(sub):
        raise ValidationError(
            "Subdomain must be 3-32 chars: lowercase letters, digits, hyphens. Must start with a letter."
        )
    if sub in RESERVED_SUBDOMAINS:
        raise ConflictError(f"'{sub}' is reserved")
    return sub


async def create_user(email: str, password: str, name: str = "") -> dict:
    email = _validate_email(email)
    _validate_password(password)
    display_name = _validate_name(name) or email.split("@")[0]

    user_id = f"user_{secrets.token_hex(12)}"
    pw_hash = hash_password(password)

    try:
        await db.insert("users", {
            "id": user_id,
            "email": email,
            "password_hash": pw_hash,
            "name": display_name,
            "role": "user",
            "balance": 0.00,
            "verified": 0,
        })
    except aiosqlite.IntegrityError:
        raise ConflictError("Email already registered")

    logger.info("User created: %s (%s)", email, user_id)
    return {
        "id": user_id,
        "email": email,
        "name": display_name,
        "role": "user",
        "balance": 0.00,
        "verified": False,
        "subdomain": None,
    }


async def authenticate(email: str, password: str) -> dict:
    email = _validate_email(email)
    user = await db.fetch_one("users", email=email)
    if not user:
        raise AuthError("Invalid email or password")
    if not verify_password(password, user["password_hash"]):
        logger.warning("Failed login: %s", email)
        raise AuthError("Invalid email or password")
    logger.info("User login: %s (%s)", email, user["id"])
    return _sanitize_user(user)


def issue_token(user: dict) -> str:
    return create_user_token(user["id"], user["email"], user.get("role", "user"))


async def get_user(user_id: str) -> dict:
    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)
    return _sanitize_user(user)


async def get_user_by_email(email: str) -> dict | None:
    email = email.strip().lower()
    user = await db.fetch_one("users", email=email)
    if not user:
        return None
    return _sanitize_user(user)


async def update_profile(user_id: str, name: str | None = None, email: str | None = None) -> dict:
    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)

    updates: dict = {}
    if name is not None:
        updates["name"] = _validate_name(name)
    if email is not None:
        new_email = _validate_email(email)
        if new_email != user["email"]:
            try:
                d = await db.get_db()
                cursor = await d.execute("SELECT id FROM users WHERE email = ? AND id != ?", (new_email, user_id))
                if await cursor.fetchone():
                    raise ConflictError("Email already in use")
            except ConflictError:
                raise
            updates["email"] = new_email

    if not updates:
        return _sanitize_user(user)

    await db.update("users", user_id, updates)
    user.update(updates)
    logger.info("Profile updated: %s → %s", user_id, list(updates.keys()))
    return _sanitize_user(user)


async def change_password(user_id: str, current_password: str, new_password: str):
    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)
    if not verify_password(current_password, user["password_hash"]):
        raise AuthError("Current password is incorrect")
    _validate_password(new_password)
    new_hash = hash_password(new_password)
    await db.update("users", user_id, {"password_hash": new_hash})
    logger.info("Password changed: %s", user_id)


async def check_subdomain_available(subdomain: str) -> bool:
    sub = _validate_subdomain(subdomain)
    d = await db.get_db()
    cursor = await d.execute("SELECT id FROM users WHERE subdomain = ?", (sub,))
    return await cursor.fetchone() is None


async def claim_subdomain(user_id: str, subdomain: str) -> str:
    sub = _validate_subdomain(subdomain)

    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)
    if user.get("subdomain"):
        raise ConflictError(f"You already have a subdomain: {user['subdomain']}")

    d = await db.get_db()
    try:
        await d.execute(
            "UPDATE users SET subdomain = ? WHERE id = ? AND subdomain IS NULL",
            (sub, user_id),
        )
        await d.commit()
    except aiosqlite.IntegrityError:
        raise ConflictError(f"'{sub}' is already taken")

    cursor = await d.execute("SELECT subdomain FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()
    if not row or row[0] != sub:
        raise ConflictError(f"'{sub}' is already taken")

    logger.info("Subdomain claimed: %s → %s", user_id, sub)
    return sub


async def list_users() -> list[dict]:
    users = await db.fetch_all("users")
    return [_sanitize_user(u) for u in users]
