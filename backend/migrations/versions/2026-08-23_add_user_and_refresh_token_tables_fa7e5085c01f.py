"""add user and refresh_token tables

Revision ID: fa7e5085c01f
Revises:
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa7e5085c01f"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="user_pkey"),
    )
    op.create_index("user_email_idx", "user", ["email"], unique=True)

    op.create_table(
        "refresh_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name="refresh_token_user_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="refresh_token_pkey"),
    )
    op.create_index("refresh_token_user_id_idx", "refresh_token", ["user_id"])
    op.create_index("refresh_token_family_id_idx", "refresh_token", ["family_id"])
    op.create_index("refresh_token_token_hash_idx", "refresh_token", ["token_hash"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("refresh_token_token_hash_idx", table_name="refresh_token")
    op.drop_index("refresh_token_family_id_idx", table_name="refresh_token")
    op.drop_index("refresh_token_user_id_idx", table_name="refresh_token")
    op.drop_table("refresh_token")

    op.drop_index("user_email_idx", table_name="user")
    op.drop_table("user")
