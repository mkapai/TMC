import hashlib
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes.messages import preview_message_resource
from api.routes.public_resources import _resolve_resource
from config import Config
from models import MessageResource, QueuedMessage, get_local_now
from services import resource_cache_service as cache_module
from services.message_queue_service import MessageQueueService
from services.resource_cache_service import ResourceCacheError, ResourceCacheService


def queued_message():
    return QueuedMessage(
        rule_name="rule",
        client_id="account-a",
        source_chat_id="-1001",
        source_message_id=42,
        message_type="document",
        delivery_mode="manual",
        status="ingesting",
    )


class DownloadClient:
    async def download_media(self, _message, file):
        Path(file).write_bytes(b"cached-resource")
        return file


@pytest.mark.asyncio
async def test_resource_cache_public_lookup_capacity_and_delete(
    session_factory, tmp_path, monkeypatch
):
    monkeypatch.setattr(Config, "RESOURCE_CACHE_DIR", str(tmp_path / "resources"))
    monkeypatch.setattr(Config, "RESOURCE_CACHE_MAX_GB", 1)
    monkeypatch.setattr(Config, "PUBLIC_RESOURCE_TTL_DAYS", 7)
    cache = ResourceCacheService()
    monkeypatch.setattr(cache_module, "_resource_cache", cache)

    async with session_factory() as db:
        message = queued_message()
        db.add(message)
        await db.flush()
        telegram = SimpleNamespace(
            media=object(),
            file=SimpleNamespace(
                size=len(b"cached-resource"),
                name="../unsafe?.bin",
                ext=".bin",
                mime_type="application/octet-stream",
            ),
        )
        resource = await cache.cache_telegram_media(db, message, telegram, DownloadClient())
        await db.commit()
        path = Path(resource.storage_path)
        token = resource.public_token
        filename = resource.file_name

    assert filename == "unsafe_.bin"
    assert len(token) == 64
    assert path.read_bytes() == b"cached-resource"
    assert resource.sha256 == hashlib.sha256(b"cached-resource").hexdigest()

    async with session_factory() as db:
        resolved, resolved_path = await _resolve_resource(token, filename, db)
        assert resolved.id == resource.id
        assert resolved_path == path.resolve()
        with pytest.raises(HTTPException) as invalid:
            await _resolve_resource(token, "../unsafe_.bin", db)
        assert invalid.value.status_code == 404

    async with session_factory() as db:
        expired_resource = await db.get(MessageResource, resource.id)
        expired_resource.created_at = get_local_now() - timedelta(days=8)
        await db.commit()
        with pytest.raises(HTTPException) as expired:
            await _resolve_resource(token, filename, db)
        assert expired.value.status_code == 404

        preview = await preview_message_resource(resource.id, db)
        assert Path(preview.path).resolve() == path.resolve()
        assert preview.headers["cache-control"] == "private, no-store"

    monkeypatch.setattr(Config, "RESOURCE_CACHE_MAX_GB", 0.000000001)
    async with session_factory() as db:
        with pytest.raises(ResourceCacheError, match="上限"):
            await cache.ensure_capacity(db, 1024)

    await MessageQueueService().delete(message.id)
    assert not path.exists()
    async with session_factory() as db:
        with pytest.raises(HTTPException) as deleted:
            await _resolve_resource(token, filename, db)
        assert deleted.value.status_code == 404
