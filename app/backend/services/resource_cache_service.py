"""Durable cache for attachments accepted into the message queue."""
import hashlib
import mimetypes
import re
import secrets
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from models import MessageResource, QueuedMessage


class ResourceCacheError(RuntimeError):
    pass


class ResourceCacheService:
    def __init__(self) -> None:
        self.root = Path(Config.RESOURCE_CACHE_DIR).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def safe_filename(value: Optional[str], fallback: str = "resource.bin") -> str:
        name = Path(value or fallback).name
        name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", name).strip(" .")
        return name[:240] or fallback

    async def current_size(self, db: AsyncSession) -> int:
        total = await db.scalar(select(func.sum(MessageResource.file_size)))
        return int(total or 0)

    async def ensure_capacity(self, db: AsyncSession, incoming_size: int) -> None:
        limit = int(Config.RESOURCE_CACHE_MAX_GB * 1024 ** 3)
        if limit > 0 and await self.current_size(db) + max(incoming_size, 0) > limit:
            raise ResourceCacheError(
                f"资源缓存已达到 {Config.RESOURCE_CACHE_MAX_GB:g} GB 上限，请删除旧消息后重试"
            )

    async def cache_telegram_media(
        self,
        db: AsyncSession,
        queued_message: QueuedMessage,
        telegram_message,
        telegram_client,
    ) -> Optional[MessageResource]:
        media = getattr(telegram_message, "media", None)
        if media is None or media.__class__.__name__ == "MessageMediaWebPage":
            return None

        file_info = getattr(telegram_message, "file", None)
        expected_size = int(getattr(file_info, "size", 0) or 0)
        await self.ensure_capacity(db, expected_size)

        original_name = getattr(file_info, "name", None)
        extension = getattr(file_info, "ext", None) or ""
        fallback = f"telegram-{queued_message.source_message_id}{extension}"
        file_name = self.safe_filename(original_name, fallback)
        mime_type = getattr(file_info, "mime_type", None) or mimetypes.guess_type(file_name)[0]

        token = secrets.token_hex(32)
        message_dir = (self.root / str(queued_message.id)).resolve()
        if self.root not in message_dir.parents:
            raise ResourceCacheError("无效的资源缓存路径")
        message_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file_name).suffix[:16]
        storage_path = message_dir / f"{token}{suffix}"

        actual_path = storage_path
        try:
            downloaded = await telegram_client.download_media(telegram_message, file=str(storage_path))
            actual_path = Path(downloaded or storage_path).resolve()
            if not actual_path.exists() or message_dir not in actual_path.parents:
                raise ResourceCacheError("Telegram 附件下载失败")

            size = actual_path.stat().st_size
            await self.ensure_capacity(db, size)
            digest = hashlib.sha256()
            with actual_path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except Exception:
            actual_path.unlink(missing_ok=True)
            try:
                message_dir.rmdir()
            except OSError:
                pass
            raise

        resource = MessageResource(
            message_id=queued_message.id,
            public_token=token,
            storage_path=str(actual_path),
            file_name=file_name,
            mime_type=mime_type,
            file_size=size,
            sha256=digest.hexdigest(),
        )
        db.add(resource)
        await db.flush()
        return resource

    def public_url(self, resource: MessageResource) -> str:
        path = f"/public/resources/{resource.public_token}/{quote(resource.file_name)}"
        return f"{Config.PUBLIC_BASE_URL}{path}" if Config.PUBLIC_BASE_URL else path

    def delete_file(self, resource: MessageResource) -> None:
        path = Path(resource.storage_path).resolve()
        if self.root == path or self.root not in path.parents:
            return
        try:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
        except OSError:
            pass


_resource_cache = None


def get_resource_cache() -> ResourceCacheService:
    global _resource_cache
    if _resource_cache is None:
        _resource_cache = ResourceCacheService()
    return _resource_cache
