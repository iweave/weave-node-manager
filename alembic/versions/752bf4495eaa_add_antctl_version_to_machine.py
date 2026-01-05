"""add_antctl_version_to_machine

Added antctl_version field to Machine table for antctl version configuration (January 5, 2026).
Defaults to None (uses latest version). When set, this version is passed as --version argument
to the antctl add command for all three antctl process managers (antctl+zen, antctl+user, antctl+sudo).

Revision ID: 752bf4495eaa
Revises: ba757077b6b0
Create Date: 2026-01-05 11:10:42.621507

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '752bf4495eaa'
down_revision: Union[str, Sequence[str], None] = 'ba757077b6b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add antctl_version column to machine table."""
    # Add antctl_version as UnicodeText with default None
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "antctl_version",
                sa.UnicodeText(),
                nullable=True,
                server_default=None,
            )
        )


def downgrade() -> None:
    """Remove antctl_version column from machine table."""
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.drop_column("antctl_version")
