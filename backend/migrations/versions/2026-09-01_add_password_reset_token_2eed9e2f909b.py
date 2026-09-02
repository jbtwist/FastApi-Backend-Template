"""add password reset token

Revision ID: 2eed9e2f909b
Revises: 91c374e5213a
Create Date: 2026-09-01 22:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2eed9e2f909b"
down_revision: str | Sequence[str] | None = "91c374e5213a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "password_reset_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="password_reset_token_user_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="password_reset_token_pkey"),
    )
    op.create_index("password_reset_token_user_id_idx", "password_reset_token", ["user_id"])
    op.create_index(
        "password_reset_token_token_hash_idx",
        "password_reset_token",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("password_reset_token_token_hash_idx", table_name="password_reset_token")
    op.drop_index("password_reset_token_user_id_idx", table_name="password_reset_token")
    op.drop_table("password_reset_token")
