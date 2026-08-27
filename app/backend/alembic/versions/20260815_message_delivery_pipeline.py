"""Replace direct forwarding and monitoring with the delivery pipeline.

Revision ID: 20260815_message_delivery_pipeline
Revises: 20251021_add_notification_types_to_rules
Create Date: 2026-08-15
"""
import json

from alembic import op
import sqlalchemy as sa


revision = "20260815_message_delivery_pipeline"
down_revision = "20251021_add_notification_types_to_rules"
branch_labels = None
depends_on = None


def _existing_tables(bind):
    return set(sa.inspect(bind).get_table_names())


def upgrade():
    bind = op.get_bind()

    op.create_table(
        "delivery_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("encrypted_config", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_delivery_targets_target_type", "delivery_targets", ["target_type"])
    op.create_index("ix_delivery_targets_is_active", "delivery_targets", ["is_active"])
    op.create_index("ix_delivery_targets_is_deleted", "delivery_targets", ["is_deleted"])

    op.add_column(
        "forward_rules",
        sa.Column("delivery_mode", sa.String(20), nullable=False, server_default="auto"),
    )
    op.create_table(
        "rule_delivery_targets",
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("forward_rules.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("delivery_targets.id", ondelete="CASCADE"), primary_key=True),
    )

    metadata = sa.MetaData()
    targets = sa.Table("delivery_targets", metadata, autoload_with=bind)
    associations = sa.Table("rule_delivery_targets", metadata, autoload_with=bind)
    rules = bind.execute(sa.text(
        "SELECT id, name, client_id, target_chat_id, target_chat_name "
        "FROM forward_rules ORDER BY id"
    )).mappings().all()
    for rule in rules:
        if not rule["target_chat_id"]:
            continue
        target_name = rule["target_chat_name"] or f"{rule['name']} Telegram目标"
        result = bind.execute(targets.insert().values(
            name=target_name,
            target_type="telegram",
            config_json=json.dumps({
                "client_id": rule["client_id"] or "main_user",
                "chat_id": str(rule["target_chat_id"]),
                "chat_name": rule["target_chat_name"],
            }, ensure_ascii=False),
            is_active=True,
            is_deleted=False,
        ))
        target_id = result.inserted_primary_key[0]
        bind.execute(associations.insert().values(rule_id=rule["id"], target_id=target_id))

    op.create_table(
        "queued_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("forward_rules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("client_id", sa.String(100), nullable=False),
        sa.Column("source_chat_id", sa.String(50), nullable=False),
        sa.Column("source_chat_name", sa.String(200), nullable=True),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.String(50), nullable=True),
        sa.Column("sender_username", sa.String(100), nullable=True),
        sa.Column("sender_name", sa.String(200), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("processed_text", sa.Text(), nullable=True),
        sa.Column("message_type", sa.String(50), nullable=False, server_default="text"),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("media_fingerprint", sa.String(128), nullable=True),
        sa.Column("delivery_mode", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("selected_target_ids", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="ingesting"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column("source_edited_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "rule_id", "client_id", "source_chat_id", "source_message_id",
            name="uq_queued_message_source",
        ),
    )
    for name, columns in (
        ("ix_queued_messages_rule_id", ["rule_id"]),
        ("ix_queued_messages_source_chat_id", ["source_chat_id"]),
        ("ix_queued_messages_content_hash", ["content_hash"]),
        ("ix_queued_messages_media_fingerprint", ["media_fingerprint"]),
        ("ix_queued_messages_status", ["status"]),
        ("ix_queued_messages_created_at", ["created_at"]),
    ):
        op.create_index(name, "queued_messages", columns)

    op.create_table(
        "message_resources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("queued_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("public_token", sa.String(64), nullable=False, unique=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_message_resources_message_id", "message_resources", ["message_id"])
    op.create_index("ix_message_resources_public_token", "message_resources", ["public_token"], unique=True)

    op.create_table(
        "delivery_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("delivery_id", sa.String(36), nullable=False, unique=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("queued_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("delivery_targets.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("message_id", "target_id", name="uq_delivery_job_message_target"),
    )
    for name, columns in (
        ("ix_delivery_jobs_message_id", ["message_id"]),
        ("ix_delivery_jobs_target_id", ["target_id"]),
        ("ix_delivery_jobs_status", ["status"]),
        ("ix_delivery_jobs_next_retry_at", ["next_retry_at"]),
        ("ix_delivery_jobs_created_at", ["created_at"]),
    ):
        op.create_index(name, "delivery_jobs", columns)
    op.create_index(
        "ix_delivery_jobs_delivery_id",
        "delivery_jobs",
        ["delivery_id"],
        unique=True,
    )

    tables = _existing_tables(bind)
    for table_name in (
        "notification_logs",
        "notification_rules",
        "resource_records",
        "resource_monitor_rules",
        "media_files",
        "download_tasks",
        "media_monitor_rules",
        "media_settings",
        "message_logs",
    ):
        if table_name in tables:
            op.drop_table(table_name)

    with op.batch_alter_table("forward_rules") as batch:
        batch.drop_column("target_chat_name")
        batch.drop_column("target_chat_id")


def downgrade():
    raise RuntimeError(
        "This migration deletes legacy monitoring and forwarding history. "
        "Restore the automatic pre-migration database backup instead."
    )
