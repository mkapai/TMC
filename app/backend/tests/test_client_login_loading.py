import asyncio
import json

import pytest
from starlette.requests import Request

from api.routes import clients as clients_route
from models import TelegramClient
from telegram_client_manager import TelegramClientManager


class FakeClient:
    def __init__(self):
        self.status_callbacks = []
        self.login_lock = asyncio.Lock()

    def add_status_callback(self, callback):
        self.status_callbacks.append(callback)


class FakeClientManager:
    def __init__(self):
        self.clients = {}
        self.loaded_config = None

    def add_client_with_config(self, client_id, client_type, config_data=None):
        client = FakeClient()
        self.clients[client_id] = client
        self.loaded_config = (client_id, client_type, config_data)
        return client


class FakeEnhancedBot:
    def __init__(self):
        self.multi_client_manager = FakeClientManager()

    def _notify_status_change(self, client_id, status, data):
        pass


def make_request(payload):
    body = json.dumps(payload).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/clients/myuser/login",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )


@pytest.mark.asyncio
async def test_login_loads_existing_client_from_database(session_factory, monkeypatch):
    async with session_factory() as session:
        session.add(TelegramClient(
            client_id="myuser",
            client_type="user",
            api_id="12345",
            api_hash="secret-hash",
            phone="+15550001111",
            is_active=True,
            auto_start=False,
        ))
        await session.commit()

    enhanced_bot = FakeEnhancedBot()
    monkeypatch.setattr(clients_route, "get_enhanced_bot", lambda: enhanced_bot)

    response = await clients_route.login_client(
        "myuser",
        make_request({"step": "invalid"}),
    )

    assert response.status_code == 400
    assert enhanced_bot.multi_client_manager.loaded_config == (
        "myuser",
        "user",
        {
            "api_id": "12345",
            "api_hash": "secret-hash",
            "phone": "+15550001111",
        },
    )
    assert "myuser" in enhanced_bot.multi_client_manager.clients


@pytest.mark.asyncio
async def test_login_rejects_overlapping_request(monkeypatch):
    enhanced_bot = FakeEnhancedBot()
    client = enhanced_bot.multi_client_manager.add_client_with_config(
        "myuser", "user", {}
    )
    await client.login_lock.acquire()
    monkeypatch.setattr(clients_route, "get_enhanced_bot", lambda: enhanced_bot)

    try:
        response = await clients_route.login_client(
            "myuser",
            make_request({"step": "send_code"}),
        )
    finally:
        client.login_lock.release()

    assert response.status_code == 409
    assert json.loads(response.body)["error_type"] == "login_in_progress"


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FailingTelethonClient:
    def __init__(self):
        self.session = FakeSession()
        self.disconnected = False

    async def connect(self):
        raise OSError("connection failed")

    async def disconnect(self):
        self.disconnected = True


@pytest.mark.asyncio
async def test_send_code_releases_session_after_connection_failure(monkeypatch):
    manager = TelegramClientManager("myuser", "user")
    manager.phone = "+15550001111"
    telethon_client = FailingTelethonClient()

    async def create_client():
        manager.client = telethon_client

    monkeypatch.setattr(manager, "_create_client", create_client)

    response = await manager.send_verification_code()

    assert response["success"] is False
    assert manager.client is None
    assert telethon_client.disconnected is True
    assert telethon_client.session.closed is True
