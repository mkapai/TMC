"""Unauthenticated, time-limited access to opaque message resource URLs."""
import math
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from database import get_db
from models import MessageResource, get_local_now
from services.resource_cache_service import get_resource_cache

router = APIRouter()


def _remaining_seconds(resource: MessageResource, now: datetime | None = None) -> int:
    now = now or get_local_now()
    created_at = resource.created_at
    if created_at.tzinfo is None:
        localize = getattr(now.tzinfo, "localize", None)
        created_at = localize(created_at) if localize else created_at.replace(tzinfo=now.tzinfo)
    expires_at = created_at.timestamp() + Config.PUBLIC_RESOURCE_TTL_DAYS * 86400
    return max(0, math.ceil(expires_at - now.timestamp()))


async def _resolve_resource(token: str, filename: str, db: AsyncSession) -> tuple[MessageResource, Path]:
    resource = (await db.execute(
        select(MessageResource).where(MessageResource.public_token == token)
    )).scalar_one_or_none()
    if not resource or filename != resource.file_name:
        raise HTTPException(404, "资源不存在")
    if _remaining_seconds(resource) <= 0:
        raise HTTPException(404, "资源不存在")
    path = Path(resource.storage_path).resolve()
    cache_root = get_resource_cache().root
    if not path.is_file() or cache_root not in path.parents:
        raise HTTPException(404, "资源不存在")
    return resource, path


@router.get("/{token}/{filename}")
async def download_resource(token: str, filename: str, db: AsyncSession = Depends(get_db)):
    resource, path = await _resolve_resource(token, filename, db)
    max_age = min(86400, _remaining_seconds(resource))
    return FileResponse(
        path,
        media_type=resource.mime_type or "application/octet-stream",
        filename=resource.file_name,
        headers={"Cache-Control": f"public, max-age={max_age}"},
    )


@router.head("/{token}/{filename}")
async def head_resource(token: str, filename: str, db: AsyncSession = Depends(get_db)):
    resource, path = await _resolve_resource(token, filename, db)
    max_age = min(86400, _remaining_seconds(resource))
    return Response(headers={
        "Content-Type": resource.mime_type or "application/octet-stream",
        "Content-Length": str(path.stat().st_size),
        "Cache-Control": f"public, max-age={max_age}",
    })
