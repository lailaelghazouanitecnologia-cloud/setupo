"""Shared test fixtures — in-memory SQLite for all tests."""
import asyncio
import sys
import os
from pathlib import Path

import pytest
import aiosqlite

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Override settings before any import touches them
os.environ["NSO_DATA_DIR"] = "/tmp/nso-test/data"
os.environ["NSO_JWT_SECRET"] = "test-secret-key-for-tests-only"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def fresh_db(tmp_path):
    """Create a fresh in-memory database for each test."""
    from core import db as db_mod

    # Open in-memory DB
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    db_mod._db = conn

    # Run migrations
    await db_mod._migrate(conn)

    yield conn

    await conn.close()
    db_mod._db = None


@pytest.fixture
def user_id():
    """A valid user_id for testing."""
    return "user_aabbccdd11223344eeff5566"


@pytest.fixture
async def test_user(fresh_db):
    """Create a test user and return their data."""
    from core import users
    user = await users.create_user("test@example.com", "password1234", "Test User")
    return user


@pytest.fixture
async def admin_user(fresh_db):
    """Create an admin user."""
    from core import db
    from server.auth.jwt import hash_password
    import secrets

    uid = f"user_{secrets.token_hex(12)}"
    await db.insert("users", {
        "id": uid,
        "email": "admin@nso.dev",
        "password_hash": hash_password("admin123"),
        "name": "Admin",
        "role": "admin",
        "balance": 0.00,
        "verified": 1,
    })
    return {"id": uid, "email": "admin@nso.dev", "role": "admin"}
