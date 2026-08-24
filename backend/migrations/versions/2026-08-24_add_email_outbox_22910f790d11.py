"""add email outbox

Revision ID: 22910f790d11
Revises: 7f2977e34cfe
Create Date: 2026-08-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "22910f790d11"
down_revision: str | Sequence[str] | None = "7f2977e34cfe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "email_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dead_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="email_outbox_user_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="email_outbox_pkey"),
    )
    op.create_index("email_outbox_user_id_idx", "email_outbox", ["user_id"])
    op.create_index("email_outbox_status_idx", "email_outbox", ["status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("email_outbox_status_idx", table_name="email_outbox")
    op.drop_index("email_outbox_user_id_idx", table_name="email_outbox")
    op.drop_table("email_outbox")
