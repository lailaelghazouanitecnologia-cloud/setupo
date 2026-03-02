"""NSO Zar — Workspace packaging, storage, and dependency resolution.

Modules:
    packer   — Create and extract .zar packages (tar.gz with manifest)
    storage  — Cloudflare R2 client (S3v4 signatures, no boto3)
    resolver — Recursive workspace dependency resolution
"""
from core.zar.packer import pack, extract, read_manifest
from core.zar.storage import R2Client
from core.zar.resolver import resolve_dependencies

__all__ = ["pack", "extract", "read_manifest", "R2Client", "resolve_dependencies"]
