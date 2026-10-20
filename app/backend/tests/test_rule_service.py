from datetime import datetime

import pytest
from sqlalchemy import select

from api.routes.rules import _serialize_rule
from models import DeliveryTarget, ForwardRule, rule_delivery_targets
from services.business_services import ForwardRuleService


@pytest.mark.asyncio
async def test_create_rule_returns_serializable_delivery_targets(session_factory):
    async with session_factory() as db:
        target = DeliveryTarget(name="target", target_type="telegram")
        db.add(target)
        await db.commit()
        target_id = target.id

    rule = await ForwardRuleService.create_rule(
        name="rule",
        source_chat_id="-1001",
        source_chat_name="source",
        destination_ids=[target_id],
    )

    data = _serialize_rule(rule)
    assert data["destination_ids"] == [target_id]
    assert data["delivery_targets"] == [
        {"id": target_id, "name": "target", "target_type": "telegram"}
    ]


@pytest.mark.asyncio
async def test_rule_times_are_stored_as_utc_and_serialized_with_timezone(session_factory, monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    async with session_factory() as db:
        target = DeliveryTarget(name="target", target_type="telegram")
        db.add(target)
        await db.commit()
        target_id = target.id

    rule = await ForwardRuleService.create_rule(
        name="timed rule",
        source_chat_id="-1001",
        source_chat_name="source",
        destination_ids=[target_id],
        time_filter_type="from_time",
        start_time="2026-08-28T02:00:00.000Z",
    )
    assert rule.start_time == datetime(2026, 8, 28, 2, 0)
    assert _serialize_rule(rule)["start_time"] == "2026-08-28T02:00:00Z"

    assert await ForwardRuleService.update_rule(
        rule.id,
        start_time="2026-08-28T03:00:00+00:00",
    ) is True
    async with session_factory() as db:
        updated_rule = await db.get(ForwardRule, rule.id)
        assert updated_rule.start_time == datetime(2026, 8, 28, 3, 0)


@pytest.mark.asyncio
async def test_delete_rule_removes_delivery_target_associations(session_factory):
    async with session_factory() as db:
        target = DeliveryTarget(name="target", target_type="telegram")
        rule = ForwardRule(name="rule", source_chat_id="-1001")
        rule.delivery_targets = [target]
        db.add(rule)
        await db.commit()
        rule_id = rule.id

    assert await ForwardRuleService.delete_rule(rule_id) is True

    async with session_factory() as db:
        assert (await db.execute(select(rule_delivery_targets))).all() == []
