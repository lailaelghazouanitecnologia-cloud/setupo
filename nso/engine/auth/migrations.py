TABLES = """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        name TEXT DEFAULT '',
        role TEXT DEFAULT 'user',
        balance REAL DEFAULT 0.00,
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
