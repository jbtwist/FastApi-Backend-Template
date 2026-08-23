"""add email verification

Revision ID: 7f2977e34cfe
Revises: fa7e5085c01f
Create Date: 2026-08-23 23:13:27.833778

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f2977e34cfe"
down_revision: Union[str, Sequence[str], None] = "fa7e5085c01f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("user", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "email_verification_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name="email_verification_token_user_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="email_verification_token_pkey"),
    )
    op.create_index(
        "email_verification_token_user_id_idx", "email_verification_token", ["user_id"]
    )
    op.create_index(
        "email_verification_token_token_hash_idx",
        "email_verification_token",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "email_verification_token_token_hash_idx", table_name="email_verification_token"
    )
    op.drop_index("email_verification_token_user_id_idx", table_name="email_verification_token")
    op.drop_table("email_verification_token")

    op.drop_column("user", "email_verified_at")
