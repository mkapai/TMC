"""Background delivery worker and Telegram/webhook adapters."""
import asyncio
import hashlib
import hmac
import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import httpx
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.orm import joinedload, selectinload

from config import Config
from database import db_manager
from log_manager import get_logger
from models import DeliveryJob, DeliveryTarget, QueuedMessage, get_local_now
from services.delivery_secret_store import get_delivery_secret_store
from services.resource_cache_service import get_resource_cache

logger = get_logger("delivery_worker", "delivery.log")
MAX_ATTEMPTS = 5
RETRY_DELAYS = (5, 30, 120, 600, 1800)


class DeliveryFailure(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, response_body: str = "", retry_after: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body[:2000]
        self.retry_after = retry_after


def decode_target_config(target: DeliveryTarget) -> dict[str, Any]:
    if target.target_type == "webhook":
        if not target.encrypted_config:
            return {}
        raw = get_delivery_secret_store().decrypt(target.encrypted_config)
        return json.loads(raw)
    return json.loads(target.config_json or "{}")


class DeliveryWorker:
    def __init__(self, poll_interval: float = 1.0, concurrency: int = 8) -> None:
        self.poll_interval = poll_interval
        self._semaphore = asyncio.Semaphore(concurrency)
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        await self._recover_interrupted_jobs()
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="delivery-worker")
        logger.info("投递 worker 已启动")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _recover_interrupted_jobs(self) -> None:
        async with db_manager.async_session() as db:
            jobs = list((await db.scalars(
                select(DeliveryJob).where(DeliveryJob.status == "sending")
            )).all())
            for job in jobs:
                job.status = "retry_wait"
                job.next_retry_at = get_local_now()
                job.last_error = "应用重启，任务等待重新投递"
            await db.commit()

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                job_ids = await self._claim_jobs()
                if job_ids:
                    await asyncio.gather(*(self._deliver_claimed(job_id) for job_id in job_ids))
                else:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"投递轮询失败: {exc}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

    async def _claim_jobs(self) -> list[int]:
        now = get_local_now()
        async with db_manager.async_session() as db:
            earlier = aliased(DeliveryJob)
            candidates = list((await db.scalars(
                select(DeliveryJob)
                .where(
                    or_(
                        DeliveryJob.status == "pending",
                        (DeliveryJob.status == "retry_wait") & (DeliveryJob.next_retry_at <= now),
                    ),
                    ~exists(select(earlier.id).where(
                        earlier.target_id == DeliveryJob.target_id,
                        earlier.id < DeliveryJob.id,
                        earlier.status.in_(("pending", "sending", "retry_wait")),
                    )),
                )
                .order_by(DeliveryJob.created_at.asc(), DeliveryJob.id.asc())
                .limit(200)
            )).all())
            claimed = []
            target_ids = set()
            for job in candidates:
                if job.target_id in target_ids:
                    continue
                target_ids.add(job.target_id)
                job.status = "sending"
                job.attempt_count += 1
                job.next_retry_at = None
                claimed.append(job.id)
                if len(claimed) >= 8:
                    break
            await db.commit()
            return claimed

    async def _deliver_claimed(self, job_id: int) -> None:
        async with self._semaphore:
            async with db_manager.async_session() as db:
                job = (await db.execute(
                    select(DeliveryJob)
                    .where(DeliveryJob.id == job_id)
                    .options(
                        joinedload(DeliveryJob.target),
                        joinedload(DeliveryJob.message).selectinload(QueuedMessage.resources),
                    )
                )).scalar_one_or_none()
                if not job or job.status != "sending":
                    return
                try:
                    if not job.target.is_active or job.target.is_deleted:
                        raise DeliveryFailure("发送目标已停用")
                    if job.target.target_type == "telegram":
                        await self._send_telegram(job)
                        response_status, response_body = None, ""
                    elif job.target.target_type == "webhook":
                        response_status, response_body = await self._send_webhook(job)
                    else:
                        raise DeliveryFailure(f"不支持的发送目标类型: {job.target.target_type}")
                    job.status = "sent"
                    job.sent_at = get_local_now()
                    job.last_error = None
                    job.response_status = response_status
                    job.response_body = response_body[:2000]
                except DeliveryFailure as exc:
                    job.last_error = str(exc)
                    job.response_status = exc.status_code
                    job.response_body = exc.response_body
                    if job.attempt_count >= MAX_ATTEMPTS or not job.target.is_active:
                        job.status = "failed"
                    else:
                        job.status = "retry_wait"
                        delay = exc.retry_after or RETRY_DELAYS[min(job.attempt_count - 1, len(RETRY_DELAYS) - 1)]
                        job.next_retry_at = get_local_now() + timedelta(seconds=max(1, delay))
                except Exception as exc:
                    job.last_error = str(exc)
                    if job.attempt_count >= MAX_ATTEMPTS:
                        job.status = "failed"
                    else:
                        job.status = "retry_wait"
                        delay = RETRY_DELAYS[min(job.attempt_count - 1, len(RETRY_DELAYS) - 1)]
                        job.next_retry_at = get_local_now() + timedelta(seconds=delay)
                await db.flush()
                await self._refresh_message_status(db, job.message_id)
                await db.commit()

    @staticmethod
    async def _run_on_client(wrapper, coroutine_factory):
        if not wrapper.loop or not wrapper.client or not wrapper.connected:
            raise DeliveryFailure("Telegram 客户端未连接")
        future = asyncio.run_coroutine_threadsafe(coroutine_factory(), wrapper.loop)
        return await asyncio.wrap_future(future)

    async def _send_telegram(self, job: DeliveryJob) -> None:
        from telegram_client_manager import multi_client_manager

        config = decode_target_config(job.target)
        wrapper = multi_client_manager.get_client(config.get("client_id", ""))
        if not wrapper:
            raise DeliveryFailure("找不到 Telegram 发送客户端")
        chat_id = config.get("chat_id")
        if not chat_id:
            raise DeliveryFailure("Telegram 目标缺少聊天 ID")
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            pass

        message = job.message
        resources = [Path(resource.storage_path) for resource in message.resources]
        missing = [str(path) for path in resources if not path.is_file()]
        if missing:
            raise DeliveryFailure(f"缓存资源不存在: {missing[0]}")
        text = message.processed_text or ""

        async def send():
            if resources:
                caption = text[:1024]
                result = await wrapper.client.send_file(chat_id, [str(path) for path in resources], caption=caption)
                if len(text) > 1024:
                    await wrapper.client.send_message(chat_id, text[1024:])
                return result
            return await wrapper.client.send_message(chat_id, text, link_preview=True)

        await self._run_on_client(wrapper, send)

    async def _send_webhook(self, job: DeliveryJob) -> tuple[int, str]:
        config = decode_target_config(job.target)
        url = config.get("url")
        if not url or not str(url).lower().startswith(("http://", "https://")):
            raise DeliveryFailure("Webhook URL 无效")
        if job.message.resources and not Config.PUBLIC_BASE_URL:
            raise DeliveryFailure("消息包含资源，但尚未配置 PUBLIC_BASE_URL")

        cache = get_resource_cache()
        payload = {
            "event": "message.delivery",
            "version": "1.0",
            "delivery_id": job.delivery_id,
            "rule": {"id": job.message.rule_id, "name": job.message.rule_name},
            "message": {
                "id": job.message.id,
                "type": job.message.message_type,
                "text": job.message.processed_text or "",
                "original_text": job.message.original_text or "",
                "source_created_at": job.message.source_created_at.isoformat() if job.message.source_created_at else None,
                "source": {
                    "client_id": job.message.client_id,
                    "chat_id": job.message.source_chat_id,
                    "chat_name": job.message.source_chat_name,
                    "message_id": job.message.source_message_id,
                },
                "sender": {
                    "id": job.message.sender_id,
                    "username": job.message.sender_username,
                    "name": job.message.sender_name,
                },
                "resources": [
                    {
                        "name": resource.file_name,
                        "mime_type": resource.mime_type,
                        "size": resource.file_size,
                        "sha256": resource.sha256,
                        "url": cache.public_url(resource),
                    }
                    for resource in job.message.resources
                ],
            },
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        headers = {
            **{str(key): str(value) for key, value in (config.get("headers") or {}).items()},
            "Content-Type": "application/json",
            "X-TMC-Delivery-Id": job.delivery_id,
            "X-TMC-Timestamp": timestamp,
        }
        if config.get("hmac_secret"):
            signature = hmac.new(
                str(config["hmac_secret"]).encode("utf-8"),
                timestamp.encode("ascii") + b"." + body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-TMC-Signature"] = f"sha256={signature}"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
                response = await client.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise DeliveryFailure(f"Webhook 请求失败: {exc}") from exc
        response_text = response.text[:2000]
        if 200 <= response.status_code < 300:
            return response.status_code, response_text
        retry_after = None
        if response.status_code == 429:
            try:
                retry_after = min(int(response.headers.get("Retry-After", "0")), 3600) or None
            except ValueError:
                try:
                    from email.utils import parsedate_to_datetime
                    retry_at = parsedate_to_datetime(response.headers["Retry-After"])
                    retry_after = min(max(1, int(retry_at.timestamp() - time.time())), 3600)
                except (KeyError, TypeError, ValueError):
                    pass
        raise DeliveryFailure(
            f"Webhook 返回 HTTP {response.status_code}",
            response.status_code,
            response_text,
            retry_after,
        )

    @staticmethod
    async def _refresh_message_status(db, message_id: int) -> None:
        message = await db.get(QueuedMessage, message_id)
        jobs = list((await db.scalars(
            select(DeliveryJob).where(DeliveryJob.message_id == message_id)
        )).all())
        statuses = {job.status for job in jobs}
        if jobs and statuses == {"sent"}:
            message.status = "sent"
        elif "sent" in statuses:
            message.status = "partially_sent"
        elif statuses and statuses <= {"failed", "cancelled"}:
            message.status = "failed"
        elif "sending" in statuses:
            message.status = "sending"
        else:
            message.status = "queued"


_delivery_worker = DeliveryWorker()


def get_delivery_worker() -> DeliveryWorker:
    return _delivery_worker
