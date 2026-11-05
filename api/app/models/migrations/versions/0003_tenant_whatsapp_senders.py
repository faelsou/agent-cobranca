"""até 5 números de disparo por empresa

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05 15:40:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "whatsapp_senders",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE tenants
        SET whatsapp_senders = jsonb_build_array(
            jsonb_build_object(
                'instance', whatsapp_instance,
                'number', COALESCE(whatsapp_number, '')
            )
        )
        WHERE whatsapp_instance IS NOT NULL
          AND whatsapp_senders = '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.drop_column("tenants", "whatsapp_senders")
