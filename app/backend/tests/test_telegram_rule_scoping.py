import pytest
from datetime import datetime, timezone
from types import SimpleNamespace

from models import ForwardRule
from services import message_queue_service
from telegram_client_manager import TelegramClientManager


@pytest.mark.asyncio
async def test_applicable_rules_are_scoped_to_the_receiving_client(session_factory):
    async with session_factory() as db:
        db.add_all([
            ForwardRule(
                name="account-a rule",
                source_chat_id="-1001",
                client_id="account-a",
                is_active=True,
            ),
            ForwardRule(
                name="account-b rule",
                source_chat_id="-1001",
                client_id="account-b",
                is_active=True,
            ),
        ])
        await db.commit()

    manager = TelegramClientManager("account-a", "user")
    rules = await manager._get_applicable_rules(-1001)

    assert [rule.name for rule in rules] == ["account-a rule"]


@pytest.mark.asyncio
async def test_rule_processing_does_not_truncate_message_text(monkeypatch):
    captured = {}

    class QueueStub:
        async def enqueue(self, rule, message, processed_text, client, media_messages=None):
            captured["processed_text"] = processed_text
            return 1

    monkeypatch.setattr(message_queue_service, "get_message_queue_service", lambda: QueueStub())
    manager = TelegramClientManager("account-a", "user")
    manager.client = object()
    manager._check_message_type = lambda rule, message: True
    manager._check_time_filter = lambda rule, message: True
    text = "x" * 5000
    rule = SimpleNamespace(
        id=1,
        name="unlimited rule",
        enable_keyword_filter=False,
        enable_regex_replace=False,
        max_message_length=10,
    )

    await manager._process_rule(rule, SimpleNamespace(text=text), event=None)

    assert captured["processed_text"] == text


def test_from_time_filter_uses_the_configured_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    manager = TelegramClientManager("account-a", "user")
    rule = SimpleNamespace(
        name="timed rule",
        time_filter_type="from_time",
        start_time=datetime(2026, 8, 28, 2, 0),
    )

    before_start = SimpleNamespace(date=datetime(2026, 8, 28, 1, 59, 59, tzinfo=timezone.utc))
    at_start = SimpleNamespace(date=datetime(2026, 8, 28, 2, 0, tzinfo=timezone.utc))

    assert manager._check_time_filter(rule, before_start) is False
    assert manager._check_time_filter(rule, at_start) is True


@pytest.mark.asyncio
async def test_history_backfill_reads_from_start_time_in_chronological_order(monkeypatch):
    manager = TelegramClientManager("account-a", "user")
    messages = [
        SimpleNamespace(id=1, date=datetime(2026, 8, 28, 2, 0, tzinfo=timezone.utc)),
        SimpleNamespace(id=2, date=datetime(2026, 8, 28, 3, 0, tzinfo=timezone.utc)),
    ]

    class ClientStub:
        def iter_messages(self, chat_id, **kwargs):
            assert chat_id == -1001
            assert kwargs == {
                "reverse": True,
                "offset_date": datetime(2026, 8, 28, 1, 59, 59, 999999, tzinfo=timezone.utc),
            }

            async def iterate():
                for message in messages:
                    yield message

            return iterate()

    rule = SimpleNamespace(
        id=7,
        name="history rule",
        is_active=True,
        client_id="account-a",
        source_chat_id="-1001",
        time_filter_type="from_time",
        start_time=datetime(2026, 8, 28, 2, 0),
        end_time=None,
    )
    async def get_rule(rule_id):
        assert rule_id == rule.id
        return rule

    processed = []
    async def process_rule(processed_rule, message, event=None, media_messages=None):
        processed.append(message.id)
        return message.id

    monkeypatch.setattr("services.business_services.ForwardRuleService.get_rule_by_id", get_rule)
    manager.client = ClientStub()
    manager._process_rule = process_rule

    await manager._backfill_rule_history(rule.id, force_full=True)

    assert processed == [1, 2]


@pytest.mark.asyncio
async def test_history_backfill_groups_album_resources(monkeypatch):
    manager = TelegramClientManager("account-a", "user")
    messages = [
        SimpleNamespace(
            id=10, text="", message="", grouped_id=99,
            date=datetime(2026, 8, 28, 2, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            id=11, text="album caption", message="album caption", grouped_id=99,
            date=datetime(2026, 8, 28, 2, 0, tzinfo=timezone.utc),
        ),
    ]

    class ClientStub:
        def iter_messages(self, _chat_id, **_kwargs):
            async def iterate():
                for message in messages:
                    yield message
            return iterate()

    rule = SimpleNamespace(
        id=8,
        name="album rule",
        is_active=True,
        client_id="account-a",
        source_chat_id="-1001",
        time_filter_type="from_time",
        start_time=datetime(2026, 8, 28, 2, 0),
        end_time=None,
    )

    async def get_rule(_rule_id):
        return rule

    processed = []

    async def process_rule(_rule, primary, event=None, media_messages=None):
        processed.append((primary.id, [message.id for message in media_messages]))
        return primary.id

    monkeypatch.setattr("services.business_services.ForwardRuleService.get_rule_by_id", get_rule)
    manager.client = ClientStub()
    manager._process_rule = process_rule

    await manager._backfill_rule_history(rule.id, force_full=True)

    assert processed == [(11, [10, 11])]
