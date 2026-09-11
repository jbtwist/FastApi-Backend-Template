"""add oauth identity

Revision ID: 6f0eb43e6840
Revises: 2eed9e2f909b
Create Date: 2026-09-11 16:30:45.958113

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6f0eb43e6840"
down_revision: str | Sequence[str] | None = "2eed9e2f909b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "oauth_identity",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_subject", sa.String(), nullable=False),
        sa.Column("email_at_link", sa.String(), nullable=True),
        sa.Column("is_private_relay", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="oauth_identity_user_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="oauth_identity_pkey"),
        sa.UniqueConstraint(
            "provider", "provider_subject", name="oauth_identity_provider_subject_key"
        ),
    )
    op.create_index("oauth_identity_user_id_idx", "oauth_identity", ["user_id"])
    op.alter_column("user", "password_hash", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    """Downgrade schema.

    Fails while any `user` row has no `password_hash` (an account created through a
    provider) rather than inventing a password for it.
    """
    op.alter_column("user", "password_hash", existing_type=sa.String(), nullable=False)
    op.drop_index("oauth_identity_user_id_idx", table_name="oauth_identity")
    op.drop_table("oauth_identity")
