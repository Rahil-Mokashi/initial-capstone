"""add testing and internal consumption quantities to fuel reconciliations

Revision ID: a6921e07076f
Revises: d6e5393626bf
Create Date: 2026-09-15 00:49:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6921e07076f'
down_revision: Union[str, Sequence[str], None] = 'd6e5393626bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('fuel_reconciliations', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('testing_quantity', sa.Numeric(12, 3), nullable=False, server_default='0')
        )
        batch_op.add_column(
            sa.Column('internal_consumption_quantity', sa.Numeric(12, 3), nullable=False, server_default='0')
        )
        batch_op.create_check_constraint(
            'ck_fuel_reconciliations_testing_non_negative', 'testing_quantity >= 0'
        )
        batch_op.create_check_constraint(
            'ck_fuel_reconciliations_internal_consumption_non_negative', 'internal_consumption_quantity >= 0'
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('fuel_reconciliations', schema=None) as batch_op:
        batch_op.drop_constraint('ck_fuel_reconciliations_internal_consumption_non_negative', type_='check')
        batch_op.drop_constraint('ck_fuel_reconciliations_testing_non_negative', type_='check')
        batch_op.drop_column('internal_consumption_quantity')
        batch_op.drop_column('testing_quantity')
