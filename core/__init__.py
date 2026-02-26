"""Setupo Core — Infrastructure management for AI agents.

Modules:
    db          — Async SQLite persistence layer
    models      — All Pydantic models
    errors      — Custom exception hierarchy
    workspace_config — config.toml reader/writer
    deploy/     — Deploy orchestration
    instances/  — Instance lifecycle management
    projects/   — Project CRUD
    providers/  — Cloud provider integrations (Vultr, Cloudflare)
    zar/        — .zar workspace packaging, R2 storage, dependency resolution
"""
