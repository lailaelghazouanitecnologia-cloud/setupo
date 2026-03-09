"""
Default workspace definitions for NSO platform components.

Each part of the NSO project is a workspace that can be independently
managed, built, packaged (.zar), and deployed.
"""

PLATFORM_WORKSPACES = [
    {
        "name": "server",
        "stack": "python",
        "description": "Central API server — FastAPI (:8000)",
        "source_dir": "server",
        "deploy": {
            "command": "venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000",
            "port": 8000,
        },
    },
    {
        "name": "agent",
        "stack": "python",
        "description": "NSO Agent — per-VPS machine service (:8081)",
        "source_dir": "instance",
        "deploy": {
            "command": "venv/bin/uvicorn main:app --host 0.0.0.0 --port 8081",
            "port": 8081,
        },
    },
    {
        "name": "dashboard",
        "stack": "node",
        "description": "Main user dashboard — Next.js",
        "source_dir": "client/dashboard",
        "deploy": {
            "command": "npm run build && npx serve -l 3000 out",
            "port": 3000,
        },
        "services": {
            "nginx": {"enabled": True, "domain": "nso.dev", "ssl": True},
        },
    },
    {
        "name": "admin",
        "stack": "node",
        "description": "Admin dashboard — Next.js (sonfazt.nso.dev)",
        "source_dir": "client/admin",
        "deploy": {
            "command": "npm run build && npx serve -l 3001 out",
            "port": 3001,
        },
        "services": {
            "nginx": {"enabled": True, "domain": "sonfazt.nso.dev", "ssl": True},
        },
    },
    {
        "name": "cli",
        "stack": "python",
        "description": "NSO CLI tool — command-line interface",
        "source_dir": "cli",
        "deploy": {
            "command": "",
            "port": 0,
        },
    },
]
