"""Remove orphan rule-target associations.

Revision ID: 20260827_cleanup_rule_targets
Revises: 20260815_message_delivery_pipeline
Create Date: 2026-08-27
"""
from alembic import op


revision = "20260827_cleanup_rule_targets"
down_revision = "20260815_message_delivery_pipeline"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DELETE FROM rule_delivery_targets
        WHERE NOT EXISTS (
            SELECT 1 FROM forward_rules
            WHERE forward_rules.id = rule_delivery_targets.rule_id
        )
        OR NOT EXISTS (
            SELECT 1 FROM delivery_targets
            WHERE delivery_targets.id = rule_delivery_targets.target_id
        )
        """
    )


def downgrade():
    # Deleted orphan associations cannot be restored safely.
    pass
