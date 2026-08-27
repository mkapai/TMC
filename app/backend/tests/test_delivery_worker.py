import asyncio
import hashlib
import hmac
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from models import DeliveryJob, DeliveryTarget, MessageResource, QueuedMessage, get_local_now
from services.delivery_worker import DeliveryFailure, DeliveryWorker


def make_message(message_id=1):
    return QueuedMessage(
        id=message_id,
        rule_name="rule",
        client_id="account-a",
        source_chat_id="-1001",
        source_chat_name="source",
        source_message_id=42,
        sender_id="99",
        sender_username="sender",
        sender_name="Test User",
        original_text="original",
        processed_text="final",
        message_type="text",
        delivery_mode="auto",
        status="queued",
        source_created_at=get_local_now(),
    )


@pytest.mark.asyncio
async def test_claims_oldest_job_per_target_and_recovers_interrupted_jobs(session_factory):
    async with session_factory() as db:
        targets = [
            DeliveryTarget(name="one", target_type="telegram", config_json="{}"),
            DeliveryTarget(name="two", target_type="telegram", config_json="{}"),
        ]
        messages = [make_message(), make_message(2), make_message(3)]
        db.add_all(targets + messages)
        await db.flush()
        jobs = [
            DeliveryJob(delivery_id="a", message_id=1, target_id=targets[0].id),
            DeliveryJob(delivery_id="b", message_id=2, target_id=targets[0].id),
            DeliveryJob(delivery_id="c", message_id=3, target_id=targets[1].id, status="sending"),
        ]
        db.add_all(jobs)
        await db.commit()

    worker = DeliveryWorker()
    await worker._recover_interrupted_jobs()
    claimed = await worker._claim_jobs()

    async with session_factory() as db:
        jobs = list((await db.scalars(select(DeliveryJob).order_by(DeliveryJob.id))).all())
        assert claimed == [jobs[0].id, jobs[2].id]
        assert [job.status for job in jobs] == ["sending", "pending", "sending"]
        assert [job.attempt_count for job in jobs] == [1, 0, 1]


@pytest.mark.asyncio
async def test_telegram_adapter_copy_sends_cached_attachment(tmp_path, monkeypatch):
    attachment = tmp_path / "asset.bin"
    attachment.write_bytes(b"asset")
    client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
    wrapper = SimpleNamespace(client=client, loop=asyncio.get_running_loop(), connected=True)
    manager = SimpleNamespace(get_client=lambda _client_id: wrapper)
    monkeypatch.setitem(
        sys.modules,
        "telegram_client_manager",
        SimpleNamespace(multi_client_manager=manager),
    )

    target = DeliveryTarget(
        id=1,
        name="telegram",
        target_type="telegram",
        config_json=json.dumps({"client_id": "account-a", "chat_id": "-2002"}),
    )
    message = make_message()
    message.resources = [MessageResource(
        public_token="f" * 64,
        storage_path=str(attachment),
        file_name="asset.bin",
        file_size=5,
        sha256=hashlib.sha256(b"asset").hexdigest(),
    )]
    job = DeliveryJob(delivery_id="delivery", target=target, message=message)

    await DeliveryWorker()._send_telegram(job)

    client.send_file.assert_awaited_once_with(-2002, [str(attachment)], caption="final")
    client.send_message.assert_not_awaited()


async def _serve_once(response: bytes):
    received = asyncio.get_running_loop().create_future()

    async def handler(reader, writer):
        header_block = await reader.readuntil(b"\r\n\r\n")
        headers = {}
        lines = header_block.decode("latin-1").split("\r\n")
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.lower()] = value.strip()
        body = await reader.readexactly(int(headers.get("content-length", "0")))
        received.set_result((headers, body))
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    return server, received, server.sockets[0].getsockname()[1]


@pytest.mark.asyncio
async def test_webhook_sends_stable_json_and_hmac(monkeypatch):
    server, received, port = await _serve_once(
        b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    )
    target = DeliveryTarget(id=1, name="hook", target_type="webhook")
    job = DeliveryJob(delivery_id="stable-delivery-id", target=target, message=make_message())
    monkeypatch.setattr(
        "services.delivery_worker.decode_target_config",
        lambda _target: {
            "url": f"http://127.0.0.1:{port}/delivery",
            "headers": {"X-Custom": "value", "X-TMC-Delivery-Id": "overridden"},
            "hmac_secret": "secret",
        },
    )

    try:
        status, _ = await DeliveryWorker()._send_webhook(job)
        headers, body = await received
    finally:
        server.close()
        await server.wait_closed()

    payload = json.loads(body)
    assert status == 204
    assert payload["event"] == "message.delivery"
    assert payload["delivery_id"] == "stable-delivery-id"
    assert headers["x-custom"] == "value"
    assert headers["x-tmc-delivery-id"] == "stable-delivery-id"
    expected = hmac.new(
        b"secret",
        headers["x-tmc-timestamp"].encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    assert headers["x-tmc-signature"] == f"sha256={expected}"


@pytest.mark.asyncio
async def test_webhook_429_exposes_retry_after(monkeypatch):
    server, _, port = await _serve_once(
        b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 17\r\n"
        b"Content-Length: 0\r\nConnection: close\r\n\r\n"
    )
    target = DeliveryTarget(id=1, name="hook", target_type="webhook")
    job = DeliveryJob(delivery_id="stable", target=target, message=make_message())
    monkeypatch.setattr(
        "services.delivery_worker.decode_target_config",
        lambda _target: {"url": f"http://127.0.0.1:{port}/delivery"},
    )

    try:
        with pytest.raises(DeliveryFailure) as raised:
            await DeliveryWorker()._send_webhook(job)
    finally:
        server.close()
        await server.wait_closed()

    assert raised.value.status_code == 429
    assert raised.value.retry_after == 17
