import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from models import DeliveryJob, DeliveryTarget, ForwardRule, QueuedMessage, get_local_now
from services.message_queue_service import MessageQueueError, MessageQueueService


def telegram_message(message_id: int, text: str = "accepted"):
    sender = SimpleNamespace(
        id=99,
        username="sender",
        first_name="Test",
        last_name="User",
    )
    return SimpleNamespace(
        id=message_id,
        text=text,
        message=text,
        media=None,
        photo=None,
        video=None,
        voice=None,
        audio=None,
        sticker=None,
        gif=None,
        document=None,
        sender=sender,
        sender_id=99,
        date=get_local_now(),
    )


async def create_rule(factory, mode="auto", deduplicate=False):
    async with factory() as db:
        targets = [
            DeliveryTarget(name="one", target_type="telegram", config_json="{}"),
            DeliveryTarget(name="two", target_type="webhook", encrypted_config="unused"),
        ]
        rule = ForwardRule(
            name=f"{mode}-rule",
            source_chat_id="-1001",
            client_id="account-a",
            delivery_mode=mode,
            enable_deduplication=deduplicate,
            dedup_check_content=True,
            dedup_check_media=True,
            dedup_time_window=3600,
        )
        rule.delivery_targets = targets
        db.add(rule)
        await db.commit()
        return rule, targets


@pytest.mark.asyncio
async def test_auto_enqueue_is_unique_and_deduplicates_content(session_factory):
    service = MessageQueueService()
    rule, targets = await create_rule(session_factory, deduplicate=True)

    first_id = await service.enqueue(rule, telegram_message(10), "normalized", None)
    repeated_id = await service.enqueue(rule, telegram_message(10), "normalized", None)
    duplicate_id = await service.enqueue(rule, telegram_message(11), "normalized", None)

    assert repeated_id == first_id
    assert duplicate_id is None
    async with session_factory() as db:
        assert await db.scalar(select(func.count(QueuedMessage.id))) == 1
        jobs = list((await db.scalars(select(DeliveryJob))).all())
        assert {job.target_id for job in jobs} == {target.id for target in targets}
        assert {job.status for job in jobs} == {"pending"}


@pytest.mark.asyncio
async def test_manual_review_selects_targets_before_approval(session_factory):
    service = MessageQueueService()
    rule, targets = await create_rule(session_factory, mode="manual")
    message_id = await service.enqueue(rule, telegram_message(20), "draft", None)

    await service.update_review(message_id, "edited", [targets[0].id])
    await service.approve(message_id)

    async with session_factory() as db:
        message = await db.get(QueuedMessage, message_id)
        jobs = list((await db.scalars(select(DeliveryJob))).all())
        assert message.status == "queued"
        assert message.processed_text == "edited"
        assert json.loads(message.selected_target_ids) == [targets[0].id]
        assert [(job.target_id, job.status) for job in jobs] == [
            (targets[0].id, "pending")
        ]


@pytest.mark.asyncio
async def test_manual_message_can_be_edited_and_pushed_atomically(session_factory):
    service = MessageQueueService()
    rule, targets = await create_rule(session_factory, mode="manual")
    message_id = await service.enqueue(rule, telegram_message(25), "draft", None)

    await service.update_review(message_id, "ready", [targets[1].id], push=True)

    async with session_factory() as db:
        message = await db.get(QueuedMessage, message_id)
        jobs = list((await db.scalars(select(DeliveryJob))).all())
        assert message.status == "queued"
        assert message.processed_text == "ready"
        assert json.loads(message.selected_target_ids) == [targets[1].id]
        assert [(job.target_id, job.status) for job in jobs] == [
            (targets[1].id, "pending")
        ]


@pytest.mark.asyncio
async def test_auto_review_cancels_and_reactivates_unsent_targets(session_factory):
    service = MessageQueueService()
    rule, targets = await create_rule(session_factory)
    message_id = await service.enqueue(rule, telegram_message(30), "draft", None)

    await service.update_review(message_id, "one target", [targets[0].id])
    async with session_factory() as db:
        jobs = list((await db.scalars(
            select(DeliveryJob).order_by(DeliveryJob.target_id)
        )).all())
        assert [job.status for job in jobs] == ["pending", "cancelled"]

    await service.update_review(message_id, "both targets", [target.id for target in targets])
    async with session_factory() as db:
        message = (await db.execute(
            select(QueuedMessage)
            .where(QueuedMessage.id == message_id)
            .options(selectinload(QueuedMessage.delivery_jobs))
        )).scalar_one()
        assert message.status == "queued"
        assert {job.status for job in message.delivery_jobs} == {"pending"}


@pytest.mark.asyncio
async def test_review_rejects_targets_outside_the_rule(session_factory):
    service = MessageQueueService()
    rule, _ = await create_rule(session_factory, mode="manual")
    async with session_factory() as db:
        outsider = DeliveryTarget(name="outside", target_type="telegram", config_json="{}")
        db.add(outsider)
        await db.commit()
    message_id = await service.enqueue(rule, telegram_message(40), "draft", None)

    with pytest.raises(MessageQueueError, match="不属于当前规则"):
        await service.update_review(message_id, "edited", [outsider.id])


@pytest.mark.asyncio
async def test_edited_message_is_rejected_only_before_delivery_starts(session_factory):
    service = MessageQueueService()
    rule, _ = await create_rule(session_factory)
    message_id = await service.enqueue(rule, telegram_message(50), "draft", None)

    assert await service.reject_edited_message(rule, 50) is True
    async with session_factory() as db:
        message = (await db.execute(
            select(QueuedMessage)
            .where(QueuedMessage.id == message_id)
            .options(selectinload(QueuedMessage.delivery_jobs))
        )).scalar_one()
        assert message.status == "rejected"
        assert {job.status for job in message.delivery_jobs} == {"cancelled"}


@pytest.mark.asyncio
async def test_edited_message_reapplies_window_deduplication(session_factory):
    service = MessageQueueService()
    rule, _ = await create_rule(session_factory, deduplicate=True)
    await service.enqueue(rule, telegram_message(60), "first", None)
    edited_id = await service.enqueue(rule, telegram_message(61), "second", None)

    await service.enqueue(rule, telegram_message(61), "first", None)

    async with session_factory() as db:
        message = (await db.execute(
            select(QueuedMessage)
            .where(QueuedMessage.id == edited_id)
            .options(selectinload(QueuedMessage.delivery_jobs))
        )).scalar_one()
        assert message.status == "rejected"
        assert "去重时间窗" in message.error_message
        assert {job.status for job in message.delivery_jobs} == {"cancelled"}


@pytest.mark.asyncio
async def test_partially_sent_message_cannot_be_deleted_while_a_job_is_sending(
    session_factory,
):
    service = MessageQueueService()
    rule, _ = await create_rule(session_factory)
    message_id = await service.enqueue(rule, telegram_message(70), "message", None)
    async with session_factory() as db:
        message = (await db.execute(
            select(QueuedMessage)
            .where(QueuedMessage.id == message_id)
            .options(selectinload(QueuedMessage.delivery_jobs))
        )).scalar_one()
        message.status = "partially_sent"
        message.delivery_jobs[0].status = "sent"
        message.delivery_jobs[1].status = "sending"
        await db.commit()

    with pytest.raises(MessageQueueError, match="正在投递"):
        await service.delete(message_id)
