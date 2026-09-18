"""add oauth link token, one identity per user

Revision ID: b3c1d9e4a7f2
Revises: 6f0eb43e6840
Create Date: 2026-09-18 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3c1d9e4a7f2"
down_revision: str | Sequence[str] | None = "6f0eb43e6840"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Fails while any `user` has more than one `oauth_identity`, rather than
    choosing which link to drop.
    """
    op.drop_index("oauth_identity_user_id_idx", table_name="oauth_identity")
    op.create_unique_constraint("oauth_identity_user_id_key", "oauth_identity", ["user_id"])

    op.create_table(
        "oauth_link_token",
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
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_subject", sa.String(), nullable=False),
        sa.Column("email_at_link", sa.String(), nullable=True),
        sa.Column("is_private_relay", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="oauth_link_token_user_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="oauth_link_token_pkey"),
    )
    op.create_index("oauth_link_token_user_id_idx", "oauth_link_token", ["user_id"])
    op.create_index(
        "oauth_link_token_token_hash_idx", "oauth_link_token", ["token_hash"], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("oauth_link_token_token_hash_idx", table_name="oauth_link_token")
    op.drop_index("oauth_link_token_user_id_idx", table_name="oauth_link_token")
    op.drop_table("oauth_link_token")

    op.drop_constraint("oauth_identity_user_id_key", "oauth_identity", type_="unique")
    op.create_index("oauth_identity_user_id_idx", "oauth_identity", ["user_id"])
