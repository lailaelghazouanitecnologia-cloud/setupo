#!/bin/bash
# NSO — PostgreSQL Setup for VPS
# Usage: bash setup-postgres.sh
#   or:  bash setup-postgres.sh --password MySecurePass --migrate /opt/nso/data/nso.db
#
# Installs PostgreSQL 16, creates the nso database and user,
# configures the environment, and optionally migrates data from SQLite.

set -euo pipefail

# ── Config ──
NSO_DIR="${NSO_DIR:-/opt/nso}"
PG_VERSION="16"
DB_NAME="nso"
DB_USER="nso"
DB_PASSWORD="${DB_PASSWORD:-}"
SQLITE_PATH=""      # Set via --migrate to migrate existing data
SKIP_INSTALL=false

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[pg]${NC} $*"; }
ok()    { echo -e "${GREEN}[pg]${NC} $*"; }
warn()  { echo -e "${YELLOW}[pg]${NC} $*"; }
error() { echo -e "${RED}[pg]${NC} $*" >&2; }
die()   { error "$*"; exit 1; }

# ── Parse args ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        --password)      DB_PASSWORD="$2"; shift 2 ;;
        --migrate)       SQLITE_PATH="$2"; shift 2 ;;
        --skip-install)  SKIP_INSTALL=true; shift ;;
        --db-name)       DB_NAME="$2"; shift 2 ;;
        --db-user)       DB_USER="$2"; shift 2 ;;
        --help)
            echo "Usage: bash setup-postgres.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --password PASS       Database password (auto-generated if not set)"
            echo "  --migrate PATH        Path to existing SQLite database to migrate"
            echo "  --skip-install        Skip PostgreSQL installation (already installed)"
            echo "  --db-name NAME        Database name (default: nso)"
            echo "  --db-user USER        Database user (default: nso)"
            echo ""
            exit 0
            ;;
        *) die "Unknown option: $1" ;;
    esac
done

# ── Preflight ──
[[ $EUID -eq 0 ]] || die "This script must be run as root (use sudo)"

# Generate password if not set
if [[ -z "$DB_PASSWORD" ]]; then
    DB_PASSWORD=$(openssl rand -hex 24)
fi

DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}"

info "NSO PostgreSQL Setup"
info "Database: ${DB_NAME} | User: ${DB_USER}"
echo ""

# ── Step 1: Install PostgreSQL ──
if [[ "$SKIP_INSTALL" != "true" ]]; then
    if command -v psql &>/dev/null; then
        INSTALLED_VER=$(psql --version | grep -oP '\d+' | head -1)
        ok "PostgreSQL ${INSTALLED_VER} already installed"
    else
        info "Installing PostgreSQL ${PG_VERSION}..."
        export DEBIAN_FRONTEND=noninteractive

        # Add PostgreSQL APT repository
        apt-get install -y -qq curl ca-certificates gnupg lsb-release > /dev/null 2>&1
        curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | \
            gpg --dearmor -o /usr/share/keyrings/postgresql-keyring.gpg 2>/dev/null
        echo "deb [signed-by=/usr/share/keyrings/postgresql-keyring.gpg] \
            http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
            > /etc/apt/sources.list.d/pgdg.list

        apt-get update -qq
        apt-get install -y -qq postgresql-${PG_VERSION} > /dev/null 2>&1

        # Ensure running
        systemctl enable postgresql
        systemctl start postgresql
        ok "PostgreSQL ${PG_VERSION} installed and running"
    fi
else
    ok "Skipping PostgreSQL installation (--skip-install)"
fi

# ── Step 2: Create database and user ──
info "Creating database and user..."

# Check if user exists
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
    info "User '${DB_USER}' already exists — updating password"
    sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" > /dev/null
else
    sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" > /dev/null
    ok "User '${DB_USER}' created"
fi

# Check if database exists
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
    ok "Database '${DB_NAME}' already exists"
else
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" > /dev/null
    ok "Database '${DB_NAME}' created"
fi

# Grant privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" > /dev/null
sudo -u postgres psql -d "${DB_NAME}" -c "GRANT ALL ON SCHEMA public TO ${DB_USER};" > /dev/null

# ── Step 3: Tune PostgreSQL for VPS ──
info "Tuning PostgreSQL for VPS..."
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"

# Detect available RAM
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_RAM_MB=$((TOTAL_RAM_KB / 1024))

# Calculate settings based on RAM
SHARED_BUFFERS=$((TOTAL_RAM_MB / 4))MB
EFFECTIVE_CACHE=$((TOTAL_RAM_MB * 3 / 4))MB
WORK_MEM=$((TOTAL_RAM_MB / 32))MB
MAINT_WORK_MEM=$((TOTAL_RAM_MB / 8))MB

# Apply tuning (append to conf, overrides defaults)
cat >> "${PG_CONF}" << PGCONF

# ── NSO tuning (auto-generated for ${TOTAL_RAM_MB}MB RAM) ──
shared_buffers = ${SHARED_BUFFERS}
effective_cache_size = ${EFFECTIVE_CACHE}
work_mem = ${WORK_MEM}
maintenance_work_mem = ${MAINT_WORK_MEM}
max_connections = 50
random_page_cost = 1.1
effective_io_concurrency = 200
wal_buffers = 16MB
min_wal_size = 100MB
max_wal_size = 1GB
checkpoint_completion_target = 0.9
PGCONF

systemctl restart postgresql
ok "PostgreSQL tuned for ${TOTAL_RAM_MB}MB RAM"

# ── Step 4: Configure NSO environment ──
info "Configuring NSO environment..."

# Update or create env file for central server
ENV_FILE="${NSO_DIR}/config/nso.env"
if [[ -f "$ENV_FILE" ]]; then
    # Remove old DATABASE_URL if present
    sed -i '/^DATABASE_URL=/d' "$ENV_FILE"
    echo "DATABASE_URL=${DATABASE_URL}" >> "$ENV_FILE"
else
    cat > "$ENV_FILE" << ENV
DATABASE_URL=${DATABASE_URL}
ENV
fi
chmod 600 "$ENV_FILE"
ok "DATABASE_URL written to ${ENV_FILE}"

# Update systemd service to include env file
NSO_SERVICE="/etc/systemd/system/nso.service"
if [[ -f "$NSO_SERVICE" ]]; then
    if ! grep -q "EnvironmentFile.*nso.env" "$NSO_SERVICE"; then
        sed -i "/\[Service\]/a EnvironmentFile=${ENV_FILE}" "$NSO_SERVICE"
        systemctl daemon-reload
        ok "Systemd service updated with env file"
    fi
fi

# ── Step 5: Migrate data from SQLite (optional) ──
if [[ -n "$SQLITE_PATH" ]]; then
    if [[ ! -f "$SQLITE_PATH" ]]; then
        warn "SQLite file not found: ${SQLITE_PATH} — skipping migration"
    else
        info "Migrating data from SQLite: ${SQLITE_PATH}"

        # Check if Python + required packages are available
        PYTHON="${NSO_DIR}/venv/bin/python3"
        if [[ ! -f "$PYTHON" ]]; then
            PYTHON=$(command -v python3)
        fi

        # Run the migration script
        MIGRATE_SCRIPT="${NSO_DIR}/base/migrate-sqlite-to-pg.py"
        if [[ ! -f "$MIGRATE_SCRIPT" ]]; then
            # Try repo path
            MIGRATE_SCRIPT="$(dirname "$0")/migrate-sqlite-to-pg.py"
        fi

        if [[ -f "$MIGRATE_SCRIPT" ]]; then
            $PYTHON "$MIGRATE_SCRIPT" \
                --sqlite "$SQLITE_PATH" \
                --pg "$DATABASE_URL" \
                && ok "Data migration complete" \
                || warn "Data migration failed — check output above"
        else
            warn "Migration script not found. Run manually:"
            echo "  python3 migrate-sqlite-to-pg.py --sqlite $SQLITE_PATH --pg $DATABASE_URL"
        fi
    fi
fi

# ── Step 6: Verify ──
info "Verifying connection..."
if PGPASSWORD="${DB_PASSWORD}" psql -h localhost -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1" > /dev/null 2>&1; then
    ok "Connection verified"
else
    die "Cannot connect to database — check PostgreSQL logs"
fi

# ── Done ──
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PostgreSQL ready for NSO!${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo -e "  Database URL:  ${BLUE}${DATABASE_URL}${NC}"
echo -e "  DB Name:       ${BLUE}${DB_NAME}${NC}"
echo -e "  DB User:       ${BLUE}${DB_USER}${NC}"
echo -e "  DB Password:   ${YELLOW}${DB_PASSWORD}${NC}"
echo -e "  RAM tuning:    ${BLUE}${TOTAL_RAM_MB}MB (shared_buffers=${SHARED_BUFFERS})${NC}"
echo ""
echo -e "  ${BLUE}Save these credentials. Add to your .env:${NC}"
echo -e "  ${YELLOW}DATABASE_URL=${DATABASE_URL}${NC}"
echo ""
echo -e "  Next: restart NSO to use PostgreSQL"
echo -e "    systemctl restart nso"
echo ""
