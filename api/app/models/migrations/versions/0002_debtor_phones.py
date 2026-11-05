"""até 5 números de WhatsApp por devedor

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05 14:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "debtors",
        sa.Column("phones", sa.ARRAY(sa.String(length=20)), server_default="{}", nullable=False),
    )
    op.execute(
        "UPDATE debtors SET phones = ARRAY[phone] "
        "WHERE phone IS NOT NULL AND cardinality(phones) = 0"
    )
    op.create_index(
        "ix_debtors_phones", "debtors", ["phones"], unique=False, postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_debtors_phones", table_name="debtors")
    op.drop_column("debtors", "phones")
