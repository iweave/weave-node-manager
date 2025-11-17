"""add_rpc_port_start_to_machine

Added rpc_port_start field to Machine table for RPC port configuration (November 17, 2025).
Defaults to 30 for backwards compatibility.

Revision ID: 7c5a573319da
Revises: ade8fcd1fc9a
Create Date: 2025-11-17 02:42:54.358394

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c5a573319da"
down_revision: Union[str, Sequence[str], None] = "ade8fcd1fc9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add rpc_port_start column to machine table."""
    # Add rpc_port_start as Integer with default 30
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "rpc_port_start", sa.Integer(), nullable=False, server_default="30"
            )
        )


def downgrade() -> None:
    """Remove rpc_port_start column from machine table."""
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.drop_column("rpc_port_start")
