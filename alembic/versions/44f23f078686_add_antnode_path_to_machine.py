"""add_antnode_path_to_machine

Added antnode_path field to Machine table for binary path configuration (November 17, 2025).
Defaults to '~/.local/bin/antnode' for backwards compatibility.

Revision ID: 44f23f078686
Revises: 7c5a573319da
Create Date: 2025-11-17 02:44:10.460266

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "44f23f078686"
down_revision: Union[str, Sequence[str], None] = "7c5a573319da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add antnode_path column to machine table."""
    # Add antnode_path as UnicodeText with default '~/.local/bin/antnode'
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "antnode_path",
                sa.UnicodeText(),
                nullable=True,
                server_default="~/.local/bin/antnode",
            )
        )


def downgrade() -> None:
    """Remove antnode_path column from machine table."""
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.drop_column("antnode_path")
