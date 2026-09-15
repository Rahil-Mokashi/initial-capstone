"""add shift_bank_deposits table

Revision ID: b23bf8cb5072
Revises: 7bbaf7f0bce1
Create Date: 2026-09-15 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b23bf8cb5072'
down_revision: Union[str, Sequence[str], None] = '7bbaf7f0bce1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'shift_bank_deposits',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('shift_cash_book_id', sa.String(length=36), nullable=False),
        sa.Column('bank_name', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('recorded_by_id', sa.String(length=36), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('amount > 0', name='ck_shift_bank_deposits_amount_positive'),
        sa.ForeignKeyConstraint(['shift_cash_book_id'], ['shift_cash_books.id']),
        sa.ForeignKeyConstraint(['recorded_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('shift_bank_deposits', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_shift_bank_deposits_shift_cash_book_id'), ['shift_cash_book_id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('shift_bank_deposits')
