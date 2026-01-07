"""add_highest_node_id_used_tracking

Adds highest_node_id_used field to Machine table for antctl port allocation tracking.

This field tracks the highest node ID ever used to prevent port conflicts when antctl
doesn't free ports after node removal. Antctl managers (antctl+user, antctl+sudo, antctl+zen)
use this to allocate node IDs without reusing deleted IDs, keeping the port formula:
port = port_start * 1000 + node_id

Revision ID: e2f4a512d24c
Revises: 752bf4495eaa
Create Date: 2026-01-07 14:52:04.004145

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f4a512d24c'
down_revision: Union[str, Sequence[str], None] = '752bf4495eaa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new column to machine table
    op.add_column('machine', sa.Column('highest_node_id_used', sa.Integer(), nullable=True))

    # Populate initial value from existing nodes (if any)
    connection = op.get_bind()

    # Get max node ID from nodes table
    max_node_id = connection.execute(
        sa.text("SELECT MAX(id) FROM node")
    ).scalar()

    if max_node_id:
        # Set highest_node_id_used to the max existing node ID
        connection.execute(
            sa.text(
                "UPDATE machine SET highest_node_id_used = :max_id WHERE id = 1"
            ),
            {"max_id": max_node_id}
        )
    else:
        # No nodes exist, initialize to 0
        connection.execute(
            sa.text(
                "UPDATE machine SET highest_node_id_used = 0 WHERE id = 1"
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove column
    op.drop_column('machine', 'highest_node_id_used')
