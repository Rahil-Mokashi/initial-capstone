"""add leave_requests table

Revision ID: e7a2c19f4b6d
Revises: 9f3c7a1b2d4e
Create Date: 2026-09-23 02:00:00.000000

Client-perspective review (2026-09-23): "Leave" existed only as one
status value on an attendance day, with no request, no reason, and no
approval trail - problemstatement.md lists it as its own entity in four
sections. Deliberately scoped narrow per the user's explicit choice: a
request + approve/reject/cancel workflow only, no leave-balance/
entitlement/accrual policy (that is real HR policy specific to the
client's pump, not something to invent).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7a2c19f4b6d'
down_revision: Union[str, Sequence[str], None] = '9f3c7a1b2d4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'leave_requests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('employee_id', sa.String(length=36), nullable=False),
        sa.Column('date_from', sa.Date(), nullable=False),
        sa.Column('date_to', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('requested_by_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_by_id', sa.String(length=36), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.CheckConstraint('date_from <= date_to', name='ck_leave_requests_date_range'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['requested_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['decided_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('leave_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_leave_requests_employee_id'), ['employee_id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('leave_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_leave_requests_employee_id'))
    op.drop_table('leave_requests')
