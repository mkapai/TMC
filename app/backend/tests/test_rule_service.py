import pytest
from sqlalchemy import select

from models import DeliveryTarget, ForwardRule, rule_delivery_targets
from services.business_services import ForwardRuleService


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
