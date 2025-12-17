"""add_antctl_path_to_machine

Added antctl_path field to Machine table for antctl binary path configuration (December 16, 2025).
Defaults to '~/.local/bin/antctl' for backwards compatibility.
Addresses macOS cron PATH issues where children of cron tasks cannot inherit PATH environment.

Revision ID: ba757077b6b0
Revises: 67fe02809d26
Create Date: 2025-12-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba757077b6b0'
down_revision: Union[str, Sequence[str], None] = '67fe02809d26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add antctl_path column to machine table."""
    # Add antctl_path as UnicodeText with default '~/.local/bin/antctl'
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "antctl_path",
                sa.UnicodeText(),
                nullable=True,
                server_default="~/.local/bin/antctl",
            )
        )


def downgrade() -> None:
    """Remove antctl_path column from machine table."""
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.drop_column("antctl_path")