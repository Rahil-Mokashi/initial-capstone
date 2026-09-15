"""add testing_volume to nozzle assignments

Revision ID: ddb899222f7c
Revises: 206042cb23d3
Create Date: 2026-09-15 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ddb899222f7c'
down_revision: Union[str, Sequence[str], None] = '206042cb23d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('nozzle_assignments', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('testing_volume', sa.Numeric(12, 3), nullable=False, server_default='0')
        )
        batch_op.create_check_constraint(
            'ck_nozzle_assignments_testing_volume_non_negative', 'testing_volume >= 0'
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('nozzle_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('ck_nozzle_assignments_testing_volume_non_negative', type_='check')
        batch_op.drop_column('testing_volume')
