"""add_max_concurrent_operations

Added max_concurrent_operations field to Machine table to control global limit on concurrent operations.
Defaults to 1 for backward compatibility (conservative behavior).

Revision ID: 00dd80bcd645
Revises: fa0ca0abff5c
Create Date: 2025-12-10 19:20:26.929677

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00dd80bcd645'
down_revision: Union[str, Sequence[str], None] = 'fa0ca0abff5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add max_concurrent_operations column to machine table."""
    # Add max_concurrent_operations as Integer with default 1
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "max_concurrent_operations",
                sa.Integer(),
                nullable=True,
                server_default="1",
            )
        )


def downgrade() -> None:
    """Remove max_concurrent_operations column from machine table."""
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.drop_column("max_concurrent_operations")
