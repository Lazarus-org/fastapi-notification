"""Reference migration for digest lease ownership and safe error codes.

Attach this revision to the host application's Alembic revision chain. Stop all
workers before upgrading so in-flight batches can be safely returned to pending.
"""

import sqlalchemy as sa
from alembic import op

revision = "notification_digest_ownership"
down_revision = None
branch_labels = ("notification_digest_claim_ownership",)
depends_on = None


def upgrade():
    """Add claim ownership and replace raw errors with safe error codes."""
    op.add_column(
        "notification_digest_batch",
        sa.Column("claim_token", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "notification_digest_batch",
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE notification_digest_batch "
            "SET last_error_code = 'delivery_failed' WHERE last_error IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE notification_digest_batch "
            "SET status = 'pending', claimed_at = NULL "
            "WHERE status = 'processing'"
        )
    )
    op.drop_column("notification_digest_batch", "last_error")


def downgrade():
    """Restore the legacy error column and remove lease-token support."""
    op.add_column(
        "notification_digest_batch",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE notification_digest_batch "
            "SET last_error = last_error_code WHERE last_error_code IS NOT NULL"
        )
    )
    op.drop_column("notification_digest_batch", "last_error_code")
    op.drop_column("notification_digest_batch", "claim_token")
