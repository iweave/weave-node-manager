"""add_log_dir_to_node

Added log_dir field to Node table for antctl integration (November 14, 2025).
Allows preservation of custom log directory paths when importing antctl nodes.

Revision ID: 62bd2784638c
Revises: eeec2af7114c
Create Date: 2025-11-16 01:41:25.518976

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62bd2784638c'
down_revision: Union[str, Sequence[str], None] = 'eeec2af7114c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add log_dir column to node table."""
    # Add log_dir as nullable UnicodeText
    with op.batch_alter_table('node', schema=None) as batch_op:
        batch_op.add_column(sa.Column('log_dir', sa.UnicodeText(), nullable=True))


def downgrade() -> None:
    """Remove log_dir column from node table."""
    with op.batch_alter_table('node', schema=None) as batch_op:
        batch_op.drop_column('log_dir')
