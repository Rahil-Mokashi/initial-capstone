"""add tenders table and tender_id to sales, payments, expenses

Revision ID: 752fd2af7475
Revises: 85b6bbb9cace
Create Date: 2026-09-15 02:30:00.000000

Schema only - no data changes. Tender rows are seeded (and existing
Sale/Payment/Expense rows backfilled with a tender_id derived from
their existing payment_method) by app/database/seed.py's _seed_tenders/
_backfill_tender_ids at application startup, the same "schema in
migrations, data in seed.py" split this project already uses for
Fuel/DEFAULT_FUEL_TYPES. See PROJECT_CONTEXT.md's Step 1 entry for
exactly what happens to historical rows (short version: CASH/CARD/
CREDIT map to their like-named tender; historical UPI rows map to
"Other", since PaymentMethod.UPI never recorded which specific app -
PhonePe or Paytm - was actually used).

tender_id is added alongside payment_method/method on all three
tables, not replacing them - Sale.payment_method, Payment.method, and
Expense.payment_method keep driving every existing consumer (credit
checks, reports, dashboards, UI dropdowns) completely unchanged.
tender_id is the new reference the settlement/reconciliation feature
(docs/daily-report-spec.md) uses going forward.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '752fd2af7475'
down_revision: Union[str, Sequence[str], None] = '85b6bbb9cace'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tenders',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('settlement_type', sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tender_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_sales_tender_id_tenders', 'tenders', ['tender_id'], ['id'])

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tender_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_payments_tender_id_tenders', 'tenders', ['tender_id'], ['id'])

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tender_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_expenses_tender_id_tenders', 'tenders', ['tender_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_constraint('fk_expenses_tender_id_tenders', type_='foreignkey')
        batch_op.drop_column('tender_id')

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_payments_tender_id_tenders', type_='foreignkey')
        batch_op.drop_column('tender_id')

    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sales_tender_id_tenders', type_='foreignkey')
        batch_op.drop_column('tender_id')

    op.drop_table('tenders')
