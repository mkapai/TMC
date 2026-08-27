"""Persistence and state transitions for accepted Telegram messages."""
import asyncio
import hashlib
import json
import uuid
from datetime import timedelta
from typing import Iterable, Optional

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from database import db_manager
from models import DeliveryJob, DeliveryTarget, ForwardRule, QueuedMessage, get_local_now
from services.resource_cache_service import get_resource_cache


EDITABLE_STATUSES = {"ingesting", "pending_review", "queued", "rejected"}


class MessageQueueError(RuntimeError):
    pass


class MessageQueueService:
    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    @staticmethod
    def media_fingerprint(message) -> Optional[str]:
        media = getattr(message, "media", None)
        if media is None or media.__class__.__name__ == "MessageMediaWebPage":
            return None
        media_id = getattr(media, "id", None)
        document = getattr(media, "document", None)
        photo = getattr(media, "photo", None)
        media_id = media_id or getattr(document, "id", None) or getattr(photo, "id", None)
        return f"{media.__class__.__name__}:{media_id or getattr(message, 'id', '')}"

    @staticmethod
    def message_type(message) -> str:
        if getattr(message, "photo", None):
            return "photo"
        if getattr(message, "video", None):
            return "video"
        if getattr(message, "voice", None):
            return "voice"
        if getattr(message, "audio", None):
            return "audio"
        if getattr(message, "sticker", None):
            return "sticker"
        if getattr(message, "gif", None):
            return "animation"
        if getattr(message, "document", None):
            return "document"
        media = getattr(message, "media", None)
        if media is not None and media.__class__.__name__ == "MessageMediaWebPage":
            return "webpage"
        return "text"

    async def _is_content_duplicate(
        self,
        db,
        rule: ForwardRule,
        content_hash: str,
        media_fingerprint: Optional[str],
        source_message_id: int,
    ) -> bool:
        if not getattr(rule, "enable_deduplication", False):
            return False

        checks = []
        if getattr(rule, "dedup_check_content", True):
            checks.append(QueuedMessage.content_hash == content_hash)
        if getattr(rule, "dedup_check_media", True) and media_fingerprint:
            checks.append(QueuedMessage.media_fingerprint == media_fingerprint)
        if not checks:
            return False

        cutoff = get_local_now() - timedelta(seconds=max(1, rule.dedup_time_window or 3600))
        duplicate_id = await db.scalar(
            select(QueuedMessage.id).where(
                QueuedMessage.rule_id == rule.id,
                QueuedMessage.source_message_id != source_message_id,
                QueuedMessage.created_at >= cutoff,
                or_(*checks),
            ).limit(1)
        )
        return duplicate_id is not None

    @staticmethod
    async def _create_jobs(
        db,
        queued_message: QueuedMessage,
        target_ids: Iterable[int],
        initial_delay: int = 0,
    ) -> int:
        unique_ids = sorted({int(target_id) for target_id in target_ids})
        if not unique_ids:
            return 0
        active_ids = list((await db.scalars(
            select(DeliveryTarget.id).where(
                DeliveryTarget.id.in_(unique_ids),
                DeliveryTarget.is_active.is_(True),
                DeliveryTarget.is_deleted.is_(False),
            )
        )).all())
        existing = {
            job.target_id: job
            for job in (await db.scalars(
                select(DeliveryJob).where(
                    DeliveryJob.message_id == queued_message.id,
                    DeliveryJob.target_id.in_(active_ids),
                )
            )).all()
        }
        available = 0
        for target_id in active_ids:
            job = existing.get(target_id)
            if job:
                if job.status == "cancelled" and job.attempt_count == 0:
                    job.status = "pending"
                    job.last_error = None
                if job.status in {"pending", "retry_wait"}:
                    available += 1
                continue
            delay = max(0, int(initial_delay or 0))
            db.add(DeliveryJob(
                delivery_id=str(uuid.uuid4()),
                message_id=queued_message.id,
                target_id=target_id,
                status="retry_wait" if delay else "pending",
                next_retry_at=get_local_now() + timedelta(seconds=delay) if delay else None,
            ))
            available += 1
        return available

    async def enqueue(self, rule: ForwardRule, message, processed_text: str, telegram_client) -> Optional[int]:
        original_text = getattr(message, "text", None) or getattr(message, "message", None) or ""
        content_hash = self.content_hash(processed_text)
        media_fingerprint = self.media_fingerprint(message)
        target_ids = [target.id for target in rule.delivery_targets if target.is_active and not target.is_deleted]

        async with db_manager.async_session() as db:
            existing = (await db.execute(
                select(QueuedMessage)
                .where(
                    QueuedMessage.rule_id == rule.id,
                    QueuedMessage.client_id == rule.client_id,
                    QueuedMessage.source_chat_id == str(rule.source_chat_id),
                    QueuedMessage.source_message_id == int(message.id),
                )
                .options(selectinload(QueuedMessage.delivery_jobs))
            )).scalar_one_or_none()

            if existing:
                if any(job.attempt_count > 0 or job.status in {"sending", "sent"} for job in existing.delivery_jobs):
                    return existing.id
                if await self._is_content_duplicate(
                    db,
                    rule,
                    content_hash,
                    media_fingerprint,
                    int(message.id),
                ):
                    for job in existing.delivery_jobs:
                        if job.status in {"pending", "retry_wait"}:
                            job.status = "cancelled"
                            job.next_retry_at = None
                    existing.status = "rejected"
                    existing.error_message = "编辑后的消息在去重时间窗内与其他消息重复"
                    existing.source_edited_at = get_local_now()
                    existing.updated_at = get_local_now()
                    await db.commit()
                    return existing.id
                existing.original_text = original_text
                existing.processed_text = processed_text
                existing.content_hash = content_hash
                existing.media_fingerprint = media_fingerprint
                existing.selected_target_ids = json.dumps(target_ids)
                existing.delivery_mode = rule.delivery_mode or "auto"
                existing.source_edited_at = get_local_now()
                existing.updated_at = get_local_now()
                if existing.status == "ingest_failed":
                    try:
                        await get_resource_cache().cache_telegram_media(
                            db, existing, message, telegram_client
                        )
                        existing.error_message = None
                    except Exception as exc:
                        existing.status = "ingest_failed"
                        existing.error_message = str(exc)
                        await db.commit()
                        return existing.id
                if existing.delivery_mode == "manual":
                    for job in existing.delivery_jobs:
                        if job.status in {"pending", "retry_wait"}:
                            job.status = "cancelled"
                    existing.status = "pending_review"
                else:
                    available = await self._create_jobs(db, existing, target_ids, rule.forward_delay)
                    existing.status = "queued" if available else "failed"
                    existing.error_message = None if existing.status == "queued" else "规则没有可用的发送目标"
                await db.commit()
                return existing.id

            if await self._is_content_duplicate(
                db, rule, content_hash, media_fingerprint, int(message.id)
            ):
                return None

            sender = getattr(message, "sender", None)
            sender_name = " ".join(filter(None, [
                getattr(sender, "first_name", None),
                getattr(sender, "last_name", None),
            ])).strip() or None
            queued = QueuedMessage(
                rule_id=rule.id,
                rule_name=rule.name,
                client_id=rule.client_id,
                source_chat_id=str(rule.source_chat_id),
                source_chat_name=rule.source_chat_name,
                source_message_id=int(message.id),
                sender_id=str(getattr(message, "sender_id", "") or "") or None,
                sender_username=getattr(sender, "username", None),
                sender_name=sender_name,
                original_text=original_text,
                processed_text=processed_text,
                message_type=self.message_type(message),
                content_hash=content_hash,
                media_fingerprint=media_fingerprint,
                delivery_mode=rule.delivery_mode or "auto",
                selected_target_ids=json.dumps(target_ids),
                status="ingesting",
                source_created_at=getattr(message, "date", None),
            )
            db.add(queued)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                return None

            try:
                await get_resource_cache().cache_telegram_media(
                    db, queued, message, telegram_client
                )
                if queued.delivery_mode == "manual":
                    queued.status = "pending_review"
                else:
                    available = await self._create_jobs(db, queued, target_ids, rule.forward_delay)
                    queued.status = "queued" if available else "failed"
                    if not available:
                        queued.error_message = "规则没有可用的发送目标"
            except Exception as exc:
                queued.status = "ingest_failed"
                queued.error_message = str(exc)

            await db.commit()
            return queued.id

    async def retry_ingest(self, message_id: int) -> int:
        async with db_manager.async_session() as db:
            queued = (await db.execute(
                select(QueuedMessage)
                .where(QueuedMessage.id == message_id)
                .options(
                    selectinload(QueuedMessage.rule).selectinload(ForwardRule.delivery_targets),
                )
            )).scalar_one_or_none()
            if not queued:
                raise MessageQueueError("消息不存在")
            if queued.status != "ingest_failed":
                raise MessageQueueError("当前消息不需要重新摄取")
            if not queued.rule:
                raise MessageQueueError("原规则已删除，无法重新摄取")
            rule = queued.rule
            source_chat_id = queued.source_chat_id
            source_message_id = queued.source_message_id
            processed_text = queued.processed_text or ""
            client_id = queued.client_id

        from telegram_client_manager import multi_client_manager

        wrapper = multi_client_manager.get_client(client_id)
        if not wrapper or not wrapper.client or not wrapper.loop or not wrapper.connected:
            raise MessageQueueError("Telegram 客户端未连接，无法重新下载附件")

        async def fetch_and_enqueue():
            chat_id = source_chat_id
            try:
                chat_id = int(chat_id)
            except (TypeError, ValueError):
                pass
            telegram_message = await wrapper.client.get_messages(chat_id, ids=source_message_id)
            if not telegram_message:
                raise MessageQueueError("Telegram 源消息不存在或不可访问")
            result = await self.enqueue(rule, telegram_message, processed_text, wrapper.client)
            if result is None:
                raise MessageQueueError("消息重新摄取失败")
            return result

        if asyncio.get_running_loop() is wrapper.loop:
            return await fetch_and_enqueue()
        future = asyncio.run_coroutine_threadsafe(fetch_and_enqueue(), wrapper.loop)
        try:
            return await asyncio.wrap_future(future)
        except MessageQueueError:
            raise
        except Exception as exc:
            raise MessageQueueError(f"附件重新摄取失败: {exc}") from exc

    async def retry(self, message_id: int) -> int:
        async with db_manager.async_session() as db:
            message = await db.get(QueuedMessage, message_id)
            if not message:
                raise MessageQueueError("消息不存在")
            ingest_failed = message.status == "ingest_failed"
        if ingest_failed:
            await self.retry_ingest(message_id)
            return 1
        return await self.retry_failed_jobs(message_id)

    async def reject_edited_message(self, rule: ForwardRule, source_message_id: int) -> bool:
        """Reject an edited message only when no target has started delivery."""
        async with db_manager.async_session() as db:
            message = (await db.execute(
                select(QueuedMessage)
                .where(
                    QueuedMessage.rule_id == rule.id,
                    QueuedMessage.client_id == rule.client_id,
                    QueuedMessage.source_chat_id == str(rule.source_chat_id),
                    QueuedMessage.source_message_id == int(source_message_id),
                )
                .options(selectinload(QueuedMessage.delivery_jobs))
            )).scalar_one_or_none()
            if not message or any(job.attempt_count > 0 or job.status == "sent" for job in message.delivery_jobs):
                return False
            for job in message.delivery_jobs:
                if job.status in {"pending", "retry_wait"}:
                    job.status = "cancelled"
            message.status = "rejected"
            message.error_message = "编辑后的消息不再满足规则过滤条件"
            message.source_edited_at = get_local_now()
            await db.commit()
            return True

    async def update_review(
        self,
        message_id: int,
        text: str,
        target_ids: list[int],
        push: bool = False,
    ) -> None:
        async with db_manager.async_session() as db:
            message = (await db.execute(
                select(QueuedMessage)
                .where(QueuedMessage.id == message_id)
                .options(
                    selectinload(QueuedMessage.delivery_jobs),
                    selectinload(QueuedMessage.rule).selectinload(ForwardRule.delivery_targets),
                )
            )).scalar_one_or_none()
            if not message:
                raise MessageQueueError("消息不存在")
            if message.status not in EDITABLE_STATUSES or any(
                job.attempt_count > 0 or job.status in {"sending", "sent"}
                for job in message.delivery_jobs
            ):
                raise MessageQueueError("消息已经开始投递，不能再编辑")
            selected = sorted({int(value) for value in target_ids})
            if not selected:
                raise MessageQueueError("至少选择一个发送目标")
            if message.rule:
                allowed_ids = {
                    target.id
                    for target in message.rule.delivery_targets
                    if target.is_active and not target.is_deleted
                }
            else:
                allowed_ids = set(json.loads(message.selected_target_ids or "[]"))
            if not set(selected).issubset(allowed_ids):
                raise MessageQueueError("发送目标不属于当前规则或已停用")

            for job in message.delivery_jobs:
                if job.target_id not in selected and job.status in {"pending", "retry_wait"}:
                    job.status = "cancelled"
                    job.next_retry_at = None

            if push:
                if message.status == "ingesting":
                    raise MessageQueueError("消息附件仍在摄取，暂时不能推送")
                available = await self._create_jobs(db, message, selected)
                if not available:
                    raise MessageQueueError("没有可用的发送目标")
                message.status = "queued"
                message.error_message = None
            elif message.delivery_mode == "auto" and message.status == "queued":
                available = await self._create_jobs(db, message, selected)
                if not available:
                    raise MessageQueueError("没有可用的发送目标")

            message.processed_text = text
            message.content_hash = self.content_hash(text)
            message.selected_target_ids = json.dumps(selected)
            message.updated_at = get_local_now()
            await db.commit()

    async def approve(self, message_id: int, target_ids: Optional[list[int]] = None) -> None:
        async with db_manager.async_session() as db:
            message = (await db.execute(
                select(QueuedMessage)
                .where(QueuedMessage.id == message_id)
                .options(selectinload(QueuedMessage.delivery_jobs))
            )).scalar_one_or_none()
            if not message:
                raise MessageQueueError("消息不存在")
            if message.status not in {"pending_review", "rejected"}:
                raise MessageQueueError("当前消息状态不能批准")
            selected = target_ids
            if selected is None:
                selected = json.loads(message.selected_target_ids or "[]")
            message.selected_target_ids = json.dumps(sorted({int(value) for value in selected}))
            available = await self._create_jobs(db, message, selected)
            if not available:
                raise MessageQueueError("没有可用的发送目标")
            message.status = "queued"
            message.error_message = None
            await db.commit()

    async def reject(self, message_id: int) -> None:
        async with db_manager.async_session() as db:
            message = await db.get(QueuedMessage, message_id)
            if not message:
                raise MessageQueueError("消息不存在")
            if message.status not in {"pending_review", "rejected"}:
                raise MessageQueueError("当前消息状态不能拒绝")
            jobs = list((await db.scalars(
                select(DeliveryJob).where(DeliveryJob.message_id == message_id)
            )).all())
            if any(job.attempt_count > 0 or job.status == "sent" for job in jobs):
                raise MessageQueueError("消息已经开始投递，不能拒绝")
            for job in jobs:
                if job.status in {"pending", "retry_wait"}:
                    job.status = "cancelled"
            message.status = "rejected"
            await db.commit()

    async def retry_failed_jobs(self, message_id: int) -> int:
        async with db_manager.async_session() as db:
            message = (await db.execute(
                select(QueuedMessage)
                .where(QueuedMessage.id == message_id)
                .options(selectinload(QueuedMessage.delivery_jobs))
            )).scalar_one_or_none()
            if not message:
                raise MessageQueueError("消息不存在")
            if message.status == "ingest_failed":
                raise MessageQueueError("附件摄取失败，请使用摄取重试")
            count = 0
            for job in message.delivery_jobs:
                if job.status in {"failed", "cancelled"}:
                    job.status = "pending"
                    job.attempt_count = 0
                    job.next_retry_at = None
                    job.last_error = None
                    count += 1
            if count:
                message.status = "queued"
                message.error_message = None
            await db.commit()
            return count

    async def delete(self, message_id: int) -> None:
        async with db_manager.async_session() as db:
            message = (await db.execute(
                select(QueuedMessage)
                .where(QueuedMessage.id == message_id)
                .options(
                    selectinload(QueuedMessage.resources),
                    selectinload(QueuedMessage.delivery_jobs),
                )
            )).scalar_one_or_none()
            if not message:
                raise MessageQueueError("消息不存在")
            if message.status == "sending" or any(
                job.status == "sending" for job in message.delivery_jobs
            ):
                raise MessageQueueError("消息正在投递，不能删除")
            resources = list(message.resources)
            await db.delete(message)
            await db.commit()
            cache = get_resource_cache()
            for resource in resources:
                cache.delete_file(resource)


_message_queue_service = MessageQueueService()


def get_message_queue_service() -> MessageQueueService:
    return _message_queue_service
