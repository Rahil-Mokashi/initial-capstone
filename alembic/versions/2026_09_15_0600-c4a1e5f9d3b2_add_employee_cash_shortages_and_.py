"""add employee_cash_shortages and employee_shortage_recoveries tables

Revision ID: c4a1e5f9d3b2
Revises: b23bf8cb5072
Create Date: 2026-09-15 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a1e5f9d3b2'
down_revision: Union[str, Sequence[str], None] = 'b23bf8cb5072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'employee_cash_shortages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('shift_reconciliation_line_id', sa.String(length=36), nullable=False),
        sa.Column('employee_id', sa.String(length=36), nullable=False),
        sa.Column('expense_id', sa.String(length=36), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('recorded_by_id', sa.String(length=36), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('amount > 0', name='ck_employee_cash_shortages_amount_positive'),
        sa.ForeignKeyConstraint(['shift_reconciliation_line_id'], ['shift_reconciliation_lines.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['expense_id'], ['expenses.id']),
        sa.ForeignKeyConstraint(['recorded_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shift_reconciliation_line_id', name='uq_employee_cash_shortages_line'),
        sa.UniqueConstraint('expense_id'),
    )
    with op.batch_alter_table('employee_cash_shortages', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_employee_cash_shortages_employee_id'), ['employee_id'],
        )

    op.create_table(
        'employee_shortage_recoveries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('employee_cash_shortage_id', sa.String(length=36), nullable=False),
        sa.Column('shift_cash_book_id', sa.String(length=36), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('recorded_by_id', sa.String(length=36), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('amount > 0', name='ck_employee_shortage_recoveries_amount_positive'),
        sa.ForeignKeyConstraint(['employee_cash_shortage_id'], ['employee_cash_shortages.id']),
        sa.ForeignKeyConstraint(['shift_cash_book_id'], ['shift_cash_books.id']),
        sa.ForeignKeyConstraint(['recorded_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('employee_shortage_recoveries', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_employee_shortage_recoveries_employee_cash_shortage_id'),
            ['employee_cash_shortage_id'],
        )
        batch_op.create_index(
            batch_op.f('ix_employee_shortage_recoveries_shift_cash_book_id'),
            ['shift_cash_book_id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('employee_shortage_recoveries')
    op.drop_table('employee_cash_shortages')
