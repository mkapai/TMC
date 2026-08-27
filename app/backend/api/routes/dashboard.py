"""Queue-focused dashboard statistics."""
from datetime import datetime, time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from database import get_db
from models import DeliveryTarget, ForwardRule, QueuedMessage, get_local_now
from services.resource_cache_service import get_resource_cache

router = APIRouter()


async def _overview(db: AsyncSession) -> dict:
    status_rows = (await db.execute(
        select(QueuedMessage.status, func.count(QueuedMessage.id))
        .group_by(QueuedMessage.status)
    )).all()
    statuses = {status: count for status, count in status_rows}
    today_start = datetime.combine(get_local_now().date(), time.min)
    today_sent = await db.scalar(
        select(func.count(QueuedMessage.id)).where(
            QueuedMessage.status.in_(("sent", "partially_sent")),
            QueuedMessage.updated_at >= today_start,
        )
    ) or 0
    cache_bytes = await get_resource_cache().current_size(db)
    return {
        "total_rules": await db.scalar(select(func.count(ForwardRule.id))) or 0,
        "active_rules": await db.scalar(
            select(func.count(ForwardRule.id)).where(ForwardRule.is_active.is_(True))
        ) or 0,
        "active_targets": await db.scalar(
            select(func.count(DeliveryTarget.id)).where(
                DeliveryTarget.is_active.is_(True),
                DeliveryTarget.is_deleted.is_(False),
            )
        ) or 0,
        "pending_review": statuses.get("pending_review", 0),
        "queued": statuses.get("queued", 0),
        "sending": statuses.get("sending", 0),
        "partially_sent": statuses.get("partially_sent", 0),
        "failed": statuses.get("failed", 0) + statuses.get("ingest_failed", 0),
        "today_sent": today_sent,
        "cache_bytes": cache_bytes,
        "cache_limit_bytes": int(Config.RESOURCE_CACHE_MAX_GB * 1024 ** 3),
    }


@router.get("/overview")
async def get_overview(db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": await _overview(db)}


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    return {"success": True, "stats": await _overview(db)}
