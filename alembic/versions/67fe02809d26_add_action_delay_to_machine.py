"""add_action_delay_to_machine

Added action_delay field to Machine table to control delay in milliseconds between actions.
Defaults to 0 for backward compatibility (no delay).

Revision ID: 67fe02809d26
Revises: 00dd80bcd645
Create Date: 2025-12-12 00:05:57.197903

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67fe02809d26'
down_revision: Union[str, Sequence[str], None] = '00dd80bcd645'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add action_delay column to machine table."""
    # Add action_delay as Integer with default 0 (milliseconds between actions)
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "action_delay",
                sa.Integer(),
                nullable=True,
                server_default="0",
            )
        )


def downgrade() -> None:
    """Remove action_delay column from machine table."""
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.drop_column("action_delay")
