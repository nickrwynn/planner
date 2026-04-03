"""dedupe resource_chunks then unique constraint on resource_id chunk_index

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM resource_chunks a
            USING resource_chunks b
            WHERE a.resource_id = b.resource_id
              AND a.chunk_index = b.chunk_index
              AND a.id > b.id
            """
        )
    )
    op.create_unique_constraint(
        "uq_resource_chunks_resource_id_chunk_index",
        "resource_chunks",
        ["resource_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_resource_chunks_resource_id_chunk_index", "resource_chunks", type_="unique")
