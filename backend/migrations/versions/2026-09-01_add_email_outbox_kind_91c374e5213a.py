"""add email outbox kind

Revision ID: 91c374e5213a
Revises: 22910f790d11
Create Date: 2026-09-01 22:05:40.740655

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91c374e5213a"
down_revision: str | Sequence[str] | None = "22910f790d11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "email_outbox",
        sa.Column("kind", sa.String(), nullable=False, server_default="verification"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("email_outbox", "kind")
