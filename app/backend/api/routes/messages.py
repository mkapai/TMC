"""Message queue management API."""
import json
from datetime import datetime, time
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from database import get_db
from models import DeliveryJob, ForwardRule, MessageResource, QueuedMessage, get_local_now
from services.message_queue_service import EDITABLE_STATUSES, MessageQueueError, get_message_queue_service
from services.resource_cache_service import get_resource_cache

router = APIRouter()


class MessageUpdate(BaseModel):
    text: str
    target_ids: list[int]
    push: bool = False


class MessageApproval(BaseModel):
    target_ids: Optional[list[int]] = None


class BulkAction(BaseModel):
    message_ids: list[int]
    action: Literal["approve", "reject", "retry", "delete"]


def _serialize(message: QueuedMessage, include_detail: bool = False) -> dict:
    cache = get_resource_cache()
    result = {
        "id": message.id,
        "rule_id": message.rule_id,
        "rule_name": message.rule_name,
        "client_id": message.client_id,
        "source_chat_id": message.source_chat_id,
        "source_chat_name": message.source_chat_name,
        "source_message_id": message.source_message_id,
        "sender_id": message.sender_id,
        "sender_username": message.sender_username,
        "sender_name": message.sender_name,
        "original_text": message.original_text,
        "processed_text": message.processed_text,
        "message_type": message.message_type,
        "delivery_mode": message.delivery_mode,
        "selected_target_ids": json.loads(message.selected_target_ids or "[]"),
        "available_target_ids": [
            target.id
            for target in message.rule.delivery_targets
            if target.is_active and not target.is_deleted
        ] if message.rule else json.loads(message.selected_target_ids or "[]"),
        "status": message.status,
        "editable": message.status in EDITABLE_STATUSES and not any(
            job.attempt_count > 0 or job.status in {"sending", "sent"}
            for job in message.delivery_jobs
        ),
        "error_message": message.error_message,
        "source_created_at": message.source_created_at.isoformat() if message.source_created_at else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "updated_at": message.updated_at.isoformat() if message.updated_at else None,
        "resources": [
            {
                "id": resource.id,
                "name": resource.file_name,
                "mime_type": resource.mime_type,
                "size": resource.file_size,
                "sha256": resource.sha256,
                "url": cache.public_url(resource),
                "preview_url": f"/api/messages/resources/{resource.id}/preview",
            }
            for resource in message.resources
        ],
        "delivery_summary": {
            status: sum(1 for job in message.delivery_jobs if job.status == status)
            for status in {job.status for job in message.delivery_jobs}
        },
    }
    if include_detail:
        result["deliveries"] = [
            {
                "id": job.id,
                "delivery_id": job.delivery_id,
                "target_id": job.target_id,
                "target_name": job.target.name if job.target else "已删除目标",
                "target_type": job.target.target_type if job.target else None,
                "status": job.status,
                "attempt_count": job.attempt_count,
                "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
                "last_error": job.last_error,
                "response_status": job.response_status,
                "response_body": job.response_body,
                "sent_at": job.sent_at.isoformat() if job.sent_at else None,
            }
            for job in message.delivery_jobs
        ]
    return result


def _options():
    return (
        selectinload(QueuedMessage.resources),
        selectinload(QueuedMessage.delivery_jobs).joinedload(DeliveryJob.target),
        selectinload(QueuedMessage.rule).selectinload(ForwardRule.delivery_targets),
    )


@router.get("")
async def list_messages(
    status: Optional[str] = None,
    rule_id: Optional[int] = None,
    source_chat_id: Optional[str] = None,
    message_type: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if status:
        filters.append(QueuedMessage.status == status)
    if rule_id:
        filters.append(QueuedMessage.rule_id == rule_id)
    if source_chat_id:
        filters.append(QueuedMessage.source_chat_id == source_chat_id)
    if message_type:
        filters.append(QueuedMessage.message_type == message_type)
    if start_date:
        filters.append(QueuedMessage.created_at >= start_date)
    if end_date:
        filters.append(QueuedMessage.created_at <= end_date)
    if search:
        value = f"%{search}%"
        filters.append(or_(
            QueuedMessage.processed_text.ilike(value),
            QueuedMessage.original_text.ilike(value),
            QueuedMessage.source_chat_name.ilike(value),
            QueuedMessage.sender_username.ilike(value),
        ))

    total = await db.scalar(select(func.count(QueuedMessage.id)).where(*filters)) or 0
    messages = list((await db.scalars(
        select(QueuedMessage)
        .where(*filters)
        .options(*_options())
        .order_by(QueuedMessage.created_at.desc(), QueuedMessage.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).all())
    return {
        "success": True,
        "messages": [_serialize(message) for message in messages],
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


@router.get("/stats")
async def message_stats(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(QueuedMessage.status, func.count(QueuedMessage.id)).group_by(QueuedMessage.status)
    )).all()
    today = get_local_now().date()
    today_start = datetime.combine(today, time.min)
    today_sent = await db.scalar(select(func.count(QueuedMessage.id)).where(
        QueuedMessage.status.in_(["sent", "partially_sent"]),
        QueuedMessage.updated_at >= today_start,
    )) or 0
    cache_bytes = await get_resource_cache().current_size(db)
    return {
        "success": True,
        "stats": {
            **{status: count for status, count in rows},
            "today_sent": today_sent,
            "cache_bytes": cache_bytes,
        },
    }


@router.get("/resources/{resource_id}/preview")
async def preview_message_resource(resource_id: int, db: AsyncSession = Depends(get_db)):
    resource = await db.get(MessageResource, resource_id)
    if not resource:
        raise HTTPException(404, "资源不存在")
    path = Path(resource.storage_path).resolve()
    cache_root = get_resource_cache().root
    if not path.is_file() or cache_root not in path.parents:
        raise HTTPException(404, "资源不存在")
    return FileResponse(
        path,
        media_type=resource.mime_type or "application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/{message_id}")
async def get_message(message_id: int, db: AsyncSession = Depends(get_db)):
    message = (await db.execute(
        select(QueuedMessage).where(QueuedMessage.id == message_id).options(*_options())
    )).scalar_one_or_none()
    if not message:
        raise HTTPException(404, "消息不存在")
    return {"success": True, "message": _serialize(message, include_detail=True)}


@router.patch("/{message_id}")
async def update_message(message_id: int, payload: MessageUpdate):
    try:
        await get_message_queue_service().update_review(
            message_id,
            payload.text,
            payload.target_ids,
            push=payload.push,
        )
        return {"success": True}
    except MessageQueueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{message_id}/approve")
async def approve_message(message_id: int, payload: MessageApproval):
    try:
        await get_message_queue_service().approve(message_id, payload.target_ids)
        return {"success": True}
    except MessageQueueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{message_id}/reject")
async def reject_message(message_id: int):
    try:
        await get_message_queue_service().reject(message_id)
        return {"success": True}
    except MessageQueueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{message_id}/retry")
async def retry_message(message_id: int):
    try:
        count = await get_message_queue_service().retry(message_id)
        return {"success": True, "retried": count}
    except MessageQueueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/{message_id}")
async def delete_message(message_id: int):
    try:
        await get_message_queue_service().delete(message_id)
        return {"success": True}
    except MessageQueueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/bulk/action")
async def bulk_action(payload: BulkAction):
    service = get_message_queue_service()
    succeeded, failed = [], []
    for message_id in sorted(set(payload.message_ids)):
        try:
            if payload.action == "approve":
                await service.approve(message_id)
            elif payload.action == "reject":
                await service.reject(message_id)
            elif payload.action == "retry":
                await service.retry(message_id)
            else:
                await service.delete(message_id)
            succeeded.append(message_id)
        except MessageQueueError as exc:
            failed.append({"id": message_id, "error": str(exc)})
    return {"success": not failed, "succeeded": succeeded, "failed": failed}
