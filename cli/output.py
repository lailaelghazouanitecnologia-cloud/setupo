"""NSO CLI — Output formatting helpers."""
import json
import sys


# ANSI colors
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Disable colors if not a terminal
if not sys.stdout.isatty():
    RED = GREEN = YELLOW = BLUE = CYAN = DIM = BOLD = RESET = ""


def ok(msg: str):
    print(f"{GREEN}OK{RESET} {msg}")


def err(msg: str):
    print(f"{RED}ERROR{RESET} {msg}", file=sys.stderr)


def warn(msg: str):
    print(f"{YELLOW}WARN{RESET} {msg}")


def info(msg: str):
    print(f"{BLUE}>{RESET} {msg}")


def dim(msg: str):
    print(f"{DIM}{msg}{RESET}")


def header(msg: str):
    print(f"\n{BOLD}{msg}{RESET}")
    print(f"{DIM}{'─' * min(len(msg) + 4, 60)}{RESET}")


def table(rows: list[dict], columns: list[str] | None = None):
    """Print a list of dicts as a formatted table."""
    if not rows:
        dim("  (empty)")
        return

    if not columns:
        columns = list(rows[0].keys())

    # Calculate column widths
    widths = {}
    for col in columns:
        widths[col] = max(
            len(col),
            max((len(str(row.get(col, ""))) for row in rows), default=0),
        )

    # Header
    hdr = "  ".join(f"{BOLD}{col:<{widths[col]}}{RESET}" for col in columns)
    print(f"  {hdr}")
    sep = "  ".join("─" * widths[col] for col in columns)
    print(f"  {DIM}{sep}{RESET}")

    # Rows
    for row in rows:
        cells = []
        for col in columns:
            val = str(row.get(col, ""))
            # Color status fields
            if col.lower() in ("status", "state"):
                if val in ("active", "running", "deployed", "ok", "complete"):
                    val = f"{GREEN}{val}{RESET}"
                elif val in ("error", "failed", "destroyed"):
                    val = f"{RED}{val}{RESET}"
                elif val in ("provisioning", "pending", "deploying"):
                    val = f"{YELLOW}{val}{RESET}"
            cells.append(f"{val:<{widths[col]}}")
        print(f"  {'  '.join(cells)}")


def as_json(data):
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=2))


def kv(data: dict, indent: int = 2):
    """Print key-value pairs."""
    if not data:
        dim("  (empty)")
        return
    max_key = max(len(str(k)) for k in data.keys())
    for k, v in data.items():
        print(f"{' ' * indent}{CYAN}{k:<{max_key}}{RESET}  {v}")
