"""add missing shift_reconciliation_lines indexes

Revision ID: fd84bd0d297b
Revises: 8451c0ddca47
Create Date: 2026-09-15 03:50:00.000000

Follow-up fix, not a rewrite of the already-committed migration it
follows: ShiftReconciliationLine.shift_reconciliation_id and .tender_id
are both declared index=True (app/models/shift_reconciliation_line.py),
but 8451c0ddca47's create_table only defined the columns and their
foreign keys, not the matching indexes - a real gap an Alembic
autogenerate compare_metadata check caught while building the next
migration in this chain. Migrations already applied/committed are
treated as history here, not edited after the fact (this project's own
convention) - this adds what was missing instead.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'fd84bd0d297b'
down_revision: Union[str, Sequence[str], None] = '8451c0ddca47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('shift_reconciliation_lines', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_shift_reconciliation_lines_shift_reconciliation_id'),
            ['shift_reconciliation_id'],
        )
        batch_op.create_index(batch_op.f('ix_shift_reconciliation_lines_tender_id'), ['tender_id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('shift_reconciliation_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shift_reconciliation_lines_tender_id'))
        batch_op.drop_index(batch_op.f('ix_shift_reconciliation_lines_shift_reconciliation_id'))
