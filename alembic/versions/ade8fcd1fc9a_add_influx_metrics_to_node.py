"""add_influx_metrics_to_node

Added InfluxDB-specific metrics fields to Node table (November 16, 2025).
Enables direct InfluxDB line protocol reporting with comprehensive node metrics.

New fields:
- gets, puts: Request counters
- mem, cpu: Process resource usage (stored × 100 for precision)
- open_connections, total_peers, bad_peers: Network metrics
- rel_records, max_records: Storage metrics
- rewards (TEXT): High-precision balance (18 decimals)
- payment_count, live_time, network_size: Economic and network metrics

Revision ID: ade8fcd1fc9a
Revises: abc5afa09a61
Create Date: 2025-11-16 01:45:03.560320

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ade8fcd1fc9a'
down_revision: Union[str, Sequence[str], None] = 'abc5afa09a61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add influx metrics columns to node table."""
    with op.batch_alter_table('node', schema=None) as batch_op:
        # Request metrics
        batch_op.add_column(sa.Column('gets', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('puts', sa.Integer(), nullable=False, server_default='0'))

        # Resource metrics (stored × 100 for precision)
        batch_op.add_column(sa.Column('mem', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('cpu', sa.Integer(), nullable=False, server_default='0'))

        # Network metrics
        batch_op.add_column(sa.Column('open_connections', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('total_peers', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('bad_peers', sa.Integer(), nullable=False, server_default='0'))

        # Storage metrics
        batch_op.add_column(sa.Column('rel_records', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('max_records', sa.Integer(), nullable=False, server_default='0'))

        # Economic metrics (rewards as TEXT for 18-decimal precision)
        batch_op.add_column(sa.Column('rewards', sa.UnicodeText(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('payment_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('live_time', sa.Integer(), nullable=False, server_default='0'))

        # Network size metric
        batch_op.add_column(sa.Column('network_size', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Remove influx metrics columns from node table."""
    with op.batch_alter_table('node', schema=None) as batch_op:
        batch_op.drop_column('network_size')
        batch_op.drop_column('live_time')
        batch_op.drop_column('payment_count')
        batch_op.drop_column('rewards')
        batch_op.drop_column('max_records')
        batch_op.drop_column('rel_records')
        batch_op.drop_column('bad_peers')
        batch_op.drop_column('total_peers')
        batch_op.drop_column('open_connections')
        batch_op.drop_column('cpu')
        batch_op.drop_column('mem')
        batch_op.drop_column('puts')
        batch_op.drop_column('gets')