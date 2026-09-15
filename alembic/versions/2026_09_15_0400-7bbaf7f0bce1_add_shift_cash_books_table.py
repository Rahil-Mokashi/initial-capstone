"""add shift_cash_books table

Revision ID: 7bbaf7f0bce1
Revises: 8451c0ddca47
Create Date: 2026-09-15 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7bbaf7f0bce1'
down_revision: Union[str, Sequence[str], None] = 'fd84bd0d297b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'shift_cash_books',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('shift_id', sa.String(length=36), nullable=False),
        sa.Column('advance_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('final_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('recorded_by_id', sa.String(length=36), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('advance_amount >= 0', name='ck_shift_cash_books_advance_non_negative'),
        sa.CheckConstraint('final_amount >= 0', name='ck_shift_cash_books_final_non_negative'),
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.id']),
        sa.ForeignKeyConstraint(['recorded_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('shift_cash_books', schema=None) as batch_op:
        # A single unique index, matching Column(unique=True, index=True)
        # exactly - see shift_reconciliations.shift_id's own original
        # migration for the identical pattern. A separate
        # UniqueConstraint plus a plain index (tried first here) is NOT
        # equivalent and shows up as drift against the model.
        batch_op.create_index(batch_op.f('ix_shift_cash_books_shift_id'), ['shift_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('shift_cash_books')
