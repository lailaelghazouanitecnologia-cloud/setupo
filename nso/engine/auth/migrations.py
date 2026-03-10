TABLES = """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        name TEXT DEFAULT '',
        role TEXT DEFAULT 'user',
        balance_cents INTEGER DEFAULT 0,
        verified INTEGER DEFAULT 0,
        subdomain TEXT UNIQUE,
        last_active TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS email_tokens (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_hash TEXT NOT NULL,
        purpose TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        expires_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    CREATE INDEX IF NOT EXISTS idx_email_tokens_hash ON email_tokens(token_hash);
    CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens(user_id);
"""


async def run_alterations(conn, logger):
    """Add balance_cents column if missing (PostgreSQL-compatible)."""
    try:
        await conn.execute("SELECT balance_cents FROM users LIMIT 1")
    except Exception:
        logger.info("Adding balance_cents column to users")
        await conn.execute("ALTER TABLE users ADD COLUMN balance_cents INTEGER DEFAULT 0")
        try:
            await conn.execute("UPDATE users SET balance_cents = CAST(ROUND(balance * 100) AS INTEGER) WHERE balance IS NOT NULL")
            logger.info("Migration complete — balance_cents populated from balance")
        except Exception:
            pass  # balance column might not exist in fresh installs
