"""add_survey_delay_to_machine

Added survey_delay field to Machine table to control delay between node surveys (November 19, 2025).
Defaults to 0 milliseconds (no delay) for backwards compatibility.

Revision ID: fa0ca0abff5c
Revises: 3249fcc20390
Create Date: 2025-11-19 23:54:46.042424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa0ca0abff5c'
down_revision: Union[str, Sequence[str], None] = '3249fcc20390'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add survey_delay column to machine table."""
    # Add survey_delay as Integer with default 0
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "survey_delay",
                sa.Integer(),
                nullable=True,
                server_default="0",
            )
        )


def downgrade() -> None:
    """Remove survey_delay column from machine table."""
    with op.batch_alter_table("machine", schema=None) as batch_op:
        batch_op.drop_column("survey_delay")
