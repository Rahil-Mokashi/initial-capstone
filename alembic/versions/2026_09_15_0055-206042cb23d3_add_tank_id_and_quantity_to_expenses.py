"""add tank_id and quantity to expenses

Revision ID: 206042cb23d3
Revises: a6921e07076f
Create Date: 2026-09-15 00:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '206042cb23d3'
down_revision: Union[str, Sequence[str], None] = 'a6921e07076f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tank_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('quantity', sa.Numeric(12, 3), nullable=True))
        batch_op.create_foreign_key('fk_expenses_tank_id_tanks', 'tanks', ['tank_id'], ['id'])
        batch_op.create_check_constraint('ck_expenses_quantity_positive', 'quantity IS NULL OR quantity > 0')
        batch_op.create_check_constraint(
            'ck_expenses_tank_id_and_quantity_together', '(tank_id IS NULL) = (quantity IS NULL)'
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_constraint('ck_expenses_tank_id_and_quantity_together', type_='check')
        batch_op.drop_constraint('ck_expenses_quantity_positive', type_='check')
        batch_op.drop_constraint('fk_expenses_tank_id_tanks', type_='foreignkey')
        batch_op.drop_column('quantity')
        batch_op.drop_column('tank_id')
