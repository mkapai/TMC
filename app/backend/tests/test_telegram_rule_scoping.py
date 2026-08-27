import pytest

from models import ForwardRule
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
