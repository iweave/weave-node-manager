"""add_delay_restart_to_machine

Added delay_restart field to Machine table for restart delay configuration (November 17, 2025).
Defaults to 600 seconds (10 minutes) for backwards compatibility.

Revision ID: 3249fcc20390
Revises: 44f23f078686
Create Date: 2025-11-17 02:44:48.805578

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3249fcc20390"
down_revision: Union[str, Sequence[str], None] = "44f23f078686"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add delay_restart column to machine table."""
    # Add delay_restart as Integer with default 600 (10 minutes)
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "delay_restart", sa.Integer(), nullable=False, server_default="600"
            )
        )


def downgrade() -> None:
    """Remove delay_restart column from machine table."""
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.drop_column("delay_restart")
