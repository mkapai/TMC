import asyncio

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from api.routes import auth as auth_route
from auth import get_password_hash
from database import get_db
from models import User
from services import login_limiter as limiter_module


@pytest_asyncio.fixture
async def login_app(session_factory, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(limiter_module, "monotonic", lambda: clock[0])
    limiter = limiter_module.LoginLimiter()
    monkeypatch.setattr(auth_route, "login_limiter", limiter)
    async with session_factory() as session:
        session.add(User(
            username="admin",
            password_hash=get_password_hash("correct-password"),
            is_active=True,
        ))
        await session.commit()

    async def override_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(auth_route.router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    return app, clock, limiter


def client_for(app, ip="192.0.2.1"):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 12345)),
        base_url="http://test",
    )


async def attempt(client, username="admin", password="wrong-password", **kwargs):
    return await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        **kwargs,
    )


@pytest.mark.asyncio
async def test_fifth_failure_bans_ip_and_correct_password_is_blocked(login_app, monkeypatch):
    app, _, _ = login_app
    async with client_for(app) as client:
        for _ in range(4):
            assert (await attempt(client)).status_code == 401
        response = await attempt(client)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "900"
        assert "IP 已临时封禁" in response.json()["detail"]

        def unexpected_verification(*args):
            pytest.fail("Banned IP must not reach password verification")

        monkeypatch.setattr(auth_route, "verify_password", unexpected_verification)
        assert (await attempt(client, password="correct-password")).status_code == 429


@pytest.mark.asyncio
async def test_unknown_users_share_ip_limit_and_other_ips_can_login(login_app):
    app, _, _ = login_app
    async with client_for(app) as client:
        for index in range(5):
            response = await attempt(client, username=f"missing-{index}")
        assert response.status_code == 429
    async with client_for(app, "192.0.2.2") as client:
        response = await attempt(client, password="correct-password")
        assert response.status_code == 200
        assert response.json()["access_token"]
        assert response.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_success_clears_previous_failures(login_app):
    app, _, _ = login_app
    async with client_for(app) as client:
        for _ in range(4):
            assert (await attempt(client)).status_code == 401
        assert (await attempt(client, password="correct-password")).status_code == 200
        for _ in range(4):
            assert (await attempt(client)).status_code == 401
        assert (await attempt(client)).status_code == 429


@pytest.mark.asyncio
async def test_ban_expires_without_being_extended_by_requests(login_app):
    app, clock, _ = login_app
    async with client_for(app) as client:
        for _ in range(5):
            await attempt(client)
        clock[0] += 899.5
        response = await attempt(client, password="correct-password")
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "1"
        clock[0] += 0.5
        assert (await attempt(client, password="correct-password")).status_code == 200
        assert (await attempt(client)).status_code == 401


@pytest.mark.asyncio
async def test_failure_window_expires(login_app):
    app, clock, _ = login_app
    async with client_for(app) as client:
        for _ in range(4):
            await attempt(client)
        clock[0] += 900
        for _ in range(4):
            assert (await attempt(client)).status_code == 401
        assert (await attempt(client)).status_code == 429


@pytest.mark.asyncio
async def test_untrusted_forwarding_headers_cannot_bypass_limit(login_app):
    app, _, _ = login_app
    async with client_for(app) as client:
        for index in range(5):
            response = await attempt(client, headers={
                "X-Forwarded-For": f"198.51.100.{index}",
                "X-Real-IP": f"198.51.100.{index}",
            })
        assert response.status_code == 429


@pytest.mark.asyncio
async def test_disabled_user_also_counts_as_failure(login_app, session_factory):
    app, _, _ = login_app
    async with session_factory() as session:
        user = await session.get(User, 1)
        user.is_active = False
        await session.commit()
    async with client_for(app) as client:
        for _ in range(4):
            assert (await attempt(client, password="correct-password")).status_code == 400
        assert (await attempt(client, password="correct-password")).status_code == 429


@pytest.mark.asyncio
async def test_concurrent_failures_do_not_lose_counts(login_app):
    app, _, _ = login_app
    async with client_for(app) as client:
        responses = await asyncio.gather(*(attempt(client) for _ in range(10)))
        statuses = [response.status_code for response in responses]
        assert statuses.count(401) == 4
        assert statuses.count(429) == 6


def test_expired_ip_records_are_cleaned_up(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(limiter_module, "monotonic", lambda: clock[0])
    limiter = limiter_module.LoginLimiter()
    limiter.record_failure("192.0.2.1")
    clock[0] += 900
    limiter.record_failure("192.0.2.2")
    assert "192.0.2.1" not in limiter._attempts
