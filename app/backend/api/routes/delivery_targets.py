"""Delivery target CRUD and connection tests."""
import asyncio
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import DeliveryTarget, rule_delivery_targets
from services.delivery_secret_store import get_delivery_secret_store
from services.delivery_worker import decode_target_config

router = APIRouter()
MASK = "********"


class DeliveryTargetPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_type: Literal["telegram", "webhook"]
    config: dict[str, Any]
    is_active: bool = True


class DeliveryTargetStatus(BaseModel):
    is_active: bool


def _validate_config(target_type: str, config: dict[str, Any]) -> None:
    if target_type == "telegram":
        if not config.get("client_id") or not str(config.get("chat_id", "")).strip():
            raise HTTPException(400, "Telegram 目标必须选择客户端和聊天")
    elif not str(config.get("url", "")).lower().startswith(("http://", "https://")):
        raise HTTPException(400, "Webhook URL 必须使用 http:// 或 https://")


def _store_config(target: DeliveryTarget, config: dict[str, Any]) -> None:
    _validate_config(target.target_type, config)
    if target.target_type == "webhook":
        target.config_json = None
        target.encrypted_config = get_delivery_secret_store().encrypt(
            json.dumps(config, ensure_ascii=False)
        )
    else:
        target.config_json = json.dumps(config, ensure_ascii=False)
        target.encrypted_config = None


def _serialize(target: DeliveryTarget, rule_count: int = 0) -> dict[str, Any]:
    config = decode_target_config(target)
    if target.target_type == "webhook":
        config = {
            "url": config.get("url", ""),
            "headers": {key: MASK for key in (config.get("headers") or {})},
            "has_hmac_secret": bool(config.get("hmac_secret")),
        }
    return {
        "id": target.id,
        "name": target.name,
        "target_type": target.target_type,
        "config": config,
        "is_active": target.is_active,
        "rule_count": rule_count,
        "created_at": target.created_at.isoformat() if target.created_at else None,
        "updated_at": target.updated_at.isoformat() if target.updated_at else None,
    }


@router.get("")
async def list_targets(db: AsyncSession = Depends(get_db)):
    counts = dict((await db.execute(
        select(rule_delivery_targets.c.target_id, func.count(rule_delivery_targets.c.rule_id))
        .group_by(rule_delivery_targets.c.target_id)
    )).all())
    targets = list((await db.scalars(
        select(DeliveryTarget)
        .where(DeliveryTarget.is_deleted.is_(False))
        .order_by(DeliveryTarget.created_at.desc())
    )).all())
    return {"success": True, "targets": [_serialize(target, counts.get(target.id, 0)) for target in targets]}


@router.post("", status_code=201)
async def create_target(payload: DeliveryTargetPayload, db: AsyncSession = Depends(get_db)):
    target = DeliveryTarget(
        name=payload.name.strip(),
        target_type=payload.target_type,
        is_active=payload.is_active,
    )
    _store_config(target, payload.config)
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return {"success": True, "target": _serialize(target)}


@router.put("/{target_id}")
async def update_target(target_id: int, payload: DeliveryTargetPayload, db: AsyncSession = Depends(get_db)):
    target = await db.get(DeliveryTarget, target_id)
    if not target or target.is_deleted:
        raise HTTPException(404, "发送目标不存在")
    config = dict(payload.config)
    if target.target_type == "webhook" and payload.target_type == "webhook":
        current = decode_target_config(target)
        headers = config.get("headers") or {}
        current_headers = current.get("headers") or {}
        config["headers"] = {
            key: current_headers.get(key, value) if value == MASK else value
            for key, value in headers.items()
        }
        if not config.get("hmac_secret") or config.get("hmac_secret") == MASK:
            config["hmac_secret"] = current.get("hmac_secret", "")
    target.name = payload.name.strip()
    target.target_type = payload.target_type
    target.is_active = payload.is_active
    _store_config(target, config)
    await db.commit()
    await db.refresh(target)
    return {"success": True, "target": _serialize(target)}


@router.delete("/{target_id}")
async def delete_target(target_id: int, db: AsyncSession = Depends(get_db)):
    target = (await db.execute(
        select(DeliveryTarget)
        .where(DeliveryTarget.id == target_id)
        .options(selectinload(DeliveryTarget.rules))
    )).scalar_one_or_none()
    if not target or target.is_deleted:
        raise HTTPException(404, "发送目标不存在")
    target.rules.clear()
    target.is_active = False
    target.is_deleted = True
    await db.commit()
    return {"success": True}


@router.patch("/{target_id}/status")
async def set_target_status(
    target_id: int,
    payload: DeliveryTargetStatus,
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(DeliveryTarget, target_id)
    if not target or target.is_deleted:
        raise HTTPException(404, "发送目标不存在")
    target.is_active = payload.is_active
    await db.commit()
    return {"success": True}


@router.post("/{target_id}/test")
async def test_target(target_id: int, db: AsyncSession = Depends(get_db)):
    target = await db.get(DeliveryTarget, target_id)
    if not target or target.is_deleted:
        raise HTTPException(404, "发送目标不存在")
    config = decode_target_config(target)
    if target.target_type == "telegram":
        from telegram_client_manager import multi_client_manager
        wrapper = multi_client_manager.get_client(config.get("client_id", ""))
        if not wrapper or not wrapper.connected or not wrapper.loop:
            raise HTTPException(400, "Telegram 客户端未连接")
        chat_id = config.get("chat_id")
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            pass
        async def get_entity():
            return await wrapper.client.get_entity(chat_id)

        future = asyncio.run_coroutine_threadsafe(get_entity(), wrapper.loop)
        try:
            entity = await asyncio.wrap_future(future)
        except Exception as exc:
            raise HTTPException(400, f"无法访问目标聊天: {exc}") from exc
        return {"success": True, "message": f"连接正常: {getattr(entity, 'title', None) or getattr(entity, 'username', chat_id)}"}

    delivery_id = str(uuid.uuid4())
    timestamp = str(int(time.time()))
    body = json.dumps({
        "event": "delivery.test",
        "version": "1.0",
        "delivery_id": delivery_id,
    }, separators=(",", ":")).encode("utf-8")
    headers = {
        **{str(key): str(value) for key, value in (config.get("headers") or {}).items()},
        "Content-Type": "application/json",
        "X-TMC-Delivery-Id": delivery_id,
        "X-TMC-Timestamp": timestamp,
    }
    if config.get("hmac_secret"):
        signature = hmac.new(
            str(config["hmac_secret"]).encode(), timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        headers["X-TMC-Signature"] = f"sha256={signature}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(config.get("url", ""), content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(400, f"Webhook 请求失败: {exc}") from exc
    if not 200 <= response.status_code < 300:
        raise HTTPException(400, f"Webhook 返回 HTTP {response.status_code}")
    return {"success": True, "message": f"Webhook 返回 HTTP {response.status_code}"}
