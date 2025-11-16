"""baseline_nov_6_2025_schema

Baseline migration representing the database schema as of November 6, 2025.
This is a no-op migration that marks existing databases as being at this baseline.

Assumes the schema has:
- Machine table with all fields except 'no_upnp'
- Node table with all fields except 'log_dir' and influx metrics
- Container table (if present)

Revision ID: eeec2af7114c
Revises:
Create Date: 2025-11-16 01:40:59.423410

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eeec2af7114c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Mark existing databases as at baseline (no-op)."""
    # This is a baseline migration for existing databases
    # No actual schema changes are made
    pass


def downgrade() -> None:
    """Cannot downgrade from baseline."""
    raise NotImplementedError("Cannot downgrade from baseline migration")
