import logging
import secrets
from datetime import datetime, timezone

import httpx

from nso.shared import db
from nso.shared.crypto import encrypt, decrypt
from nso.shared.errors import NotFoundError, ConflictError, NsoError
from nso.config import settings

logger = logging.getLogger("nso.infrastructure.database")

# ── Helpers ──────────────────────────────────────────────────────

AGENT_TIMEOUT = 120.0
AGENT_LOGIN_TIMEOUT = 10.0


def _gen_id() -> str:
    return f"db_{secrets.token_hex(8)}"


def _gen_password() -> str:
    return secrets.token_urlsafe(24)


def _ipv4_client(timeout: float = AGENT_TIMEOUT) -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    return httpx.AsyncClient(timeout=timeout, transport=transport)


async def _agent_login(ip: str) -> str:
    """Login to agent on the given instance IP and return JWT token."""
    email = settings.ADMIN_EMAIL
    password = settings.AGENT_ADMIN_PASSWORD or settings.ADMIN_PASSWORD
    if not password:
        raise NsoError(500, "AGENT_ADMIN_PASSWORD not configured")

    async with _ipv4_client(AGENT_LOGIN_TIMEOUT) as client:
        resp = await client.post(
            f"http://{ip}:8081/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code != 200:
            raise NsoError(502, f"Agent login failed ({resp.status_code})")
        return resp.json()["token"]


async def _agent_exec(ip: str, command: str, timeout: int = 60) -> tuple[str, int]:
    """Execute a command on an instance via the agent."""
    token = await _agent_login(ip)
    async with _ipv4_client(timeout + 10) as client:
        resp = await client.post(
            f"http://{ip}:8081/exec/",
            headers={"Authorization": f"Bearer {token}"},
            json={"command": command, "timeout": timeout},
        )
        if resp.status_code != 200:
            return f"Agent exec error ({resp.status_code}): {resp.text}", 1
        data = resp.json()
        output = data.get("stdout", "") + data.get("stderr", "")
        return output, data.get("exit_code", 0)


# ── NSO-managed DB host ──────────────────────────────────────────

# All managed databases run on NSO infrastructure, not user instances.
# The DB host is configurable via NSO_MANAGED_DB_HOST env var.
NSO_DB_HOST_IP = settings.MANAGED_DB_HOST
NSO_DB_INSTANCE_ID = None  # NULL = managed by NSO infrastructure (no FK reference)


async def _get_db_host_ip(record: dict) -> str:
    """Resolve the IP where this database runs."""
    instance_id = record.get("instance_id")
    if not instance_id:
        return NSO_DB_HOST_IP
    # Legacy: DB was created on a user instance
    inst = await db.fetch_one("instances", id=instance_id)
    if not inst:
        return NSO_DB_HOST_IP  # fallback
    return inst.get("ip") or NSO_DB_HOST_IP


# ── CRUD ─────────────────────────────────────────────────────────

async def create_database(project_id: str, name: str, *,
                          engine: str = "postgresql", version: str = "16") -> dict:
    """Create a managed database on NSO infrastructure."""
    # Check for duplicate name
    existing = await db.fetch_all("managed_databases", project_id=project_id, name=name)
    if existing:
        raise ConflictError(f"Database '{name}' already exists in this project")

    db_id = _gen_id()
    db_user = f"nso_{name.replace('-', '_')[:20]}"
    db_password = _gen_password()
    ip = NSO_DB_HOST_IP

    record = {
        "id": db_id,
        "project_id": project_id,
        "instance_id": NSO_DB_INSTANCE_ID,
        "name": name,
        "engine": engine,
        "version": version,
        "host": ip,
        "port": 5432,
        "db_user": db_user,
        "password_encrypted": encrypt(db_password),
        "state": "creating",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.insert("managed_databases", record)

    # Provision PostgreSQL on NSO infrastructure
    try:
        await _provision_postgres(ip, name, db_user, db_password, version)
        await db.update("managed_databases", db_id, {
            "state": "running",
            "ready_at": datetime.now(timezone.utc).isoformat(),
        })
        record["state"] = "running"
        logger.info("Created managed database %s for project %s", name, project_id)
    except Exception as e:
        await db.update("managed_databases", db_id, {
            "state": "error",
            "error": str(e)[:500],
        })
        record["state"] = "error"
        record["error"] = str(e)[:500]
        logger.error("Failed to create database %s: %s", name, e)

    return record


async def _provision_postgres(ip: str, db_name: str, db_user: str, db_password: str, version: str):
    """Install PostgreSQL (if needed) and create database + user on the instance."""
    # Step 1: Install PostgreSQL
    install_cmd = (
        f"export DEBIAN_FRONTEND=noninteractive && "
        f"which psql >/dev/null 2>&1 || ("
        f"apt-get update -y && "
        f"apt-get install -y postgresql postgresql-contrib"
        f") && systemctl enable postgresql && systemctl start postgresql"
    )
    out, code = await _agent_exec(ip, install_cmd, timeout=120)
    if code != 0:
        raise NsoError(500, f"PostgreSQL install failed: {out[-300:]}")

    # Step 2: Create user and database
    # Use single quotes in SQL, escape the password
    safe_password = db_password.replace("'", "''")
    create_cmd = (
        f"sudo -u postgres psql -c "
        f"\"DO \\$\\$ BEGIN "
        f"  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{db_user}') THEN "
        f"    CREATE ROLE {db_user} WITH LOGIN PASSWORD '{safe_password}'; "
        f"  END IF; "
        f"END \\$\\$;\" && "
        f"sudo -u postgres psql -c "
        f"\"SELECT 1 FROM pg_database WHERE datname = '{db_name}'\" | grep -q 1 || "
        f"sudo -u postgres createdb -O {db_user} {db_name}"
    )
    out, code = await _agent_exec(ip, create_cmd, timeout=30)
    if code != 0:
        raise NsoError(500, f"Database creation failed: {out[-300:]}")

    # Step 3: Allow remote connections (listen on all interfaces)
    pg_conf_cmd = (
        "PG_CONF=$(find /etc/postgresql -name postgresql.conf -type f | head -1) && "
        "grep -q \"listen_addresses = '\\*'\" \"$PG_CONF\" || "
        "(echo \"listen_addresses = '*'\" >> \"$PG_CONF\") && "
        "PG_HBA=$(find /etc/postgresql -name pg_hba.conf -type f | head -1) && "
        f"grep -q '{db_user}' \"$PG_HBA\" || "
        f"(echo 'host {db_name} {db_user} 0.0.0.0/0 scram-sha-256' >> \"$PG_HBA\") && "
        "systemctl reload postgresql"
    )
    out, code = await _agent_exec(ip, pg_conf_cmd, timeout=15)
    if code != 0:
        logger.warning("PostgreSQL remote access config may have failed: %s", out[-200:])


async def list_databases(project_id: str) -> list[dict]:
    return await db.fetch_all("managed_databases", project_id=project_id)


async def get_database(project_id: str, database_id: str) -> dict:
    record = await db.fetch_one("managed_databases", id=database_id)
    if not record or record.get("project_id") != project_id:
        raise NotFoundError("Database", database_id)
    return record


async def delete_database(project_id: str, database_id: str):
    record = await get_database(project_id, database_id)
    ip = await _get_db_host_ip(record)

    # Drop DB and user on the instance
    try:
        drop_cmd = (
            f"sudo -u postgres dropdb --if-exists {record['name']} && "
            f"sudo -u postgres dropuser --if-exists {record['db_user']}"
        )
        await _agent_exec(ip, drop_cmd, timeout=15)
    except Exception as e:
        logger.warning("Failed to drop database on instance: %s", e)

    await db.delete("managed_databases", database_id)
    logger.info("Deleted database %s", database_id)


async def execute_query(project_id: str, database_id: str, sql: str) -> dict:
    """Execute SQL on a managed database and return results."""
    record = await get_database(project_id, database_id)
    if record["state"] != "running":
        raise NsoError(400, "Database is not running")

    ip = await _get_db_host_ip(record)

    # Use JSON output from psql for reliable parsing (no CSV comma issues)
    db_password = decrypt(record["password_encrypted"])
    # Wrap query in a JSON-producing SQL wrapper
    json_sql = (
        f"SELECT json_agg(row_to_json(t)) AS data FROM ({sql}) t"
    )
    cmd = (
        f"PGPASSWORD='{db_password}' "
        f"psql -h 127.0.0.1 -p {record['port']} -U {record['db_user']} "
        f"-d {record['name']} -t -A "
        f"-c \"$(echo {_shell_b64(json_sql)} | base64 -d)\""
    )
    out, code = await _agent_exec(ip, cmd, timeout=30)

    if code != 0:
        # Fallback: try running the original SQL directly (for non-SELECT statements)
        cmd_raw = (
            f"PGPASSWORD='{db_password}' "
            f"psql -h 127.0.0.1 -p {record['port']} -U {record['db_user']} "
            f"-d {record['name']} -t -A "
            f"-c \"$(echo {_shell_b64(sql)} | base64 -d)\""
        )
        out, code = await _agent_exec(ip, cmd_raw, timeout=30)
        if code != 0:
            return {"ok": False, "error": out.strip(), "rows": []}
        return {"ok": True, "rows": [], "row_count": 0, "output": out.strip()}

    # Parse JSON output
    import json as _json
    rows = []
    raw = out.strip()
    if raw and raw != "null" and raw != "":
        try:
            rows = _json.loads(raw)
            if not isinstance(rows, list):
                rows = []
        except _json.JSONDecodeError:
            return {"ok": False, "error": f"Failed to parse query result: {raw[:200]}", "rows": []}

    return {"ok": True, "rows": rows, "row_count": len(rows)}


def _shell_b64(text: str) -> str:
    """Base64-encode text for safe shell transport."""
    import base64
    return base64.b64encode(text.encode()).decode()


async def get_database_status(project_id: str, database_id: str) -> dict:
    """Get live status of a managed database (size, connections, uptime)."""
    record = await get_database(project_id, database_id)
    if record["state"] != "running":
        return {"state": record["state"], "error": record.get("error", "")}

    ip = await _get_db_host_ip(record)

    status_sql = (
        f"SELECT pg_database_size('{record['name']}') as size_bytes, "
        f"(SELECT count(*) FROM pg_stat_activity WHERE datname='{record['name']}') as connections"
    )
    db_password = decrypt(record["password_encrypted"])
    cmd = (
        f"PGPASSWORD='{db_password}' "
        f"psql -h 127.0.0.1 -U {record['db_user']} -d {record['name']} -t -A -F ',' "
        f"-c \"$(echo {_shell_b64(status_sql)} | base64 -d)\""
    )

    try:
        out, code = await _agent_exec(ip, cmd, timeout=10)
        if code == 0 and out.strip():
            parts = out.strip().split(",")
            size_bytes = int(parts[0]) if parts[0].isdigit() else 0
            connections = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            # Update cached size
            size_mb = round(size_bytes / (1024 * 1024), 2)
            await db.update("managed_databases", database_id, {"size_mb": size_mb})
            return {
                "state": "running",
                "size_bytes": size_bytes,
                "size_mb": size_mb,
                "connections": connections,
            }
    except Exception as e:
        logger.warning("Status check failed for %s: %s", database_id, e)

    return {"state": record["state"], "size_mb": record.get("size_mb", 0)}
