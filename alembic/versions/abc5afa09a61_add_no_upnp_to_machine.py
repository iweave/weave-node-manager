"""add_no_upnp_to_machine

Added no_upnp field to Machine table for configurable UPnP control (November 15, 2025).
Defaults to True (UPnP enabled) for backwards compatibility.

Revision ID: abc5afa09a61
Revises: 62bd2784638c
Create Date: 2025-11-16 01:42:49.226515

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abc5afa09a61'
down_revision: Union[str, Sequence[str], None] = '62bd2784638c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add no_upnp column to machine table."""
    # Add no_upnp as Integer (SQLite boolean) with default 1 (True/enabled)
    with op.batch_alter_table('machine', schema=None) as batch_op:
        batch_op.add_column(sa.Column('no_upnp', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    """Remove no_upnp column from machine table."""
    with op.batch_alter_table('machine', schema=None) as batch_op:
        batch_op.drop_column('no_upnp')
