"""
z86 S3-compatible API routes.

Implements the S3 subset used by R2Client:
  PUT    /{bucket}/{key}            → upload
  GET    /{bucket}/{key}            → download
  DELETE /{bucket}/{key}            → delete
  HEAD   /{bucket}/{key}            → exists check
  GET    /{bucket}?prefix=&list-type=2 → list objects (XML)

All requests authenticated via AWS4-HMAC-SHA256.
"""
import hashlib
import logging
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Request, Response, HTTPException

from z86.auth import authenticate_request, check_bucket_access
from z86.storage import engine

logger = logging.getLogger("z86.s3")

router = APIRouter()


@router.api_route("/{bucket}/{key:path}", methods=["PUT"])
async def put_object(bucket: str, key: str, request: Request):
    """Upload an object (S3 PUT)."""
    key_record = await authenticate_request(request)
    if not check_bucket_access(key_record, bucket):
        raise HTTPException(403, "Access denied to bucket")

    data = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream")

    # Verify content hash if provided
    declared_hash = request.headers.get("x-amz-content-sha256", "")
    if declared_hash and declared_hash != "UNSIGNED-PAYLOAD":
        actual_hash = hashlib.sha256(data).hexdigest()
        if declared_hash != actual_hash:
            raise HTTPException(400, "Content SHA256 mismatch")

    try:
        result = await engine.put_object(bucket, key, data, content_type)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return Response(
        content="",
        status_code=200,
        headers={
            "ETag": f'"{result["sha256"]}"',
            "x-amz-request-id": "z86",
        },
    )


@router.api_route("/{bucket}/{key:path}", methods=["GET"])
async def get_object(bucket: str, key: str, request: Request):
    """Download an object (S3 GET)."""
    key_record = await authenticate_request(request)
    if not check_bucket_access(key_record, bucket):
        raise HTTPException(403, "Access denied to bucket")

    result = await engine.get_object(bucket, key)
    if result is None:
        raise HTTPException(404, "NoSuchKey")

    data, meta = result
    return Response(
        content=data,
        status_code=200,
        media_type=meta.get("content_type", "application/octet-stream"),
        headers={
            "Content-Length": str(len(data)),
            "ETag": f'"{meta["sha256"]}"',
            "Last-Modified": meta.get("updated_at", ""),
            "x-amz-request-id": "z86",
        },
    )


@router.api_route("/{bucket}/{key:path}", methods=["HEAD"])
async def head_object(bucket: str, key: str, request: Request):
    """Check if object exists (S3 HEAD)."""
    key_record = await authenticate_request(request)
    if not check_bucket_access(key_record, bucket):
        raise HTTPException(403, "Access denied to bucket")

    meta = await engine.head_object(bucket, key)
    if meta is None:
        raise HTTPException(404, "NoSuchKey")

    return Response(
        content="",
        status_code=200,
        headers={
            "Content-Length": str(meta["size"]),
            "Content-Type": meta.get("content_type", "application/octet-stream"),
            "ETag": f'"{meta["sha256"]}"',
            "Last-Modified": meta.get("updated_at", ""),
            "x-amz-request-id": "z86",
        },
    )


@router.api_route("/{bucket}/{key:path}", methods=["DELETE"])
async def delete_object(bucket: str, key: str, request: Request):
    """Delete an object (S3 DELETE)."""
    key_record = await authenticate_request(request)
    if not check_bucket_access(key_record, bucket):
        raise HTTPException(403, "Access denied to bucket")

    await engine.delete_object(bucket, key)
    return Response(content="", status_code=204)


@router.api_route("/{bucket}", methods=["GET"])
async def list_objects(bucket: str, request: Request):
    """List objects with prefix (S3 ListObjectsV2 — XML response)."""
    key_record = await authenticate_request(request)
    if not check_bucket_access(key_record, bucket):
        raise HTTPException(403, "Access denied to bucket")

    prefix = request.query_params.get("prefix", "")
    max_keys = int(request.query_params.get("max-keys", "1000"))

    try:
        result = await engine.list_objects(bucket, prefix=prefix, max_keys=max_keys)
    except ValueError as e:
        raise HTTPException(404, str(e))

    # Build S3-compatible XML response
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">',
        f"  <Name>{xml_escape(bucket)}</Name>",
        f"  <Prefix>{xml_escape(prefix)}</Prefix>",
        f"  <MaxKeys>{max_keys}</MaxKeys>",
        f"  <KeyCount>{result['count']}</KeyCount>",
        f"  <IsTruncated>{'true' if result['is_truncated'] else 'false'}</IsTruncated>",
    ]

    for obj in result["objects"]:
        xml_parts.append("  <Contents>")
        xml_parts.append(f"    <Key>{xml_escape(obj['key'])}</Key>")
        xml_parts.append(f"    <Size>{obj['size']}</Size>")
        xml_parts.append(f"    <LastModified>{obj['updated_at']}</LastModified>")
        xml_parts.append(f'    <ETag>"{obj["sha256"]}"</ETag>')
        xml_parts.append("  </Contents>")

    xml_parts.append("</ListBucketResult>")
    xml_body = "\n".join(xml_parts)

    return Response(
        content=xml_body,
        status_code=200,
        media_type="application/xml",
    )
