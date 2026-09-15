"""reshape shift_reconciliation cash/upi/card columns into per-tender lines

Revision ID: 8451c0ddca47
Revises: 752fd2af7475
Create Date: 2026-09-15 03:00:00.000000

The riskiest migration in this project to date - it rewrites a table
holding real shift reconciliations. Sequenced carefully so no figure
is ever lost:

  1. Create the new shift_reconciliation_lines table (empty).
  2. Idempotently ensure the "Cash", "Card", and "Other" tenders exist
     - app/database/seed.py's _seed_tenders may not have run yet if
       this migration executes in the same upgrade_to_head() call that
       first creates the tenders table (a fresh install, or an install
       jumping straight from before the tenders migration to after this
       one in a single launch). Matched by name, so a real _seed_tenders
       run later simply finds them already present and does nothing.
  3. Copy every existing shift_reconciliations row's nine cash/upi/card
     columns into three new lines each - ALWAYS all three, even when a
     figure is exactly 0.00, since the old schema always had all three
     columns and a legitimate zero is real data, not absence. This step
     runs BEFORE the old columns are dropped, while their values still
     exist to read.
  4. Only then drop the nine old columns.

"UPI" maps to the "Other" tender, not a specific UPI app - the same
mapping app/core/constants.py's PAYMENT_METHOD_TO_TENDER_NAME already
uses for Sale/Payment/Expense, for the identical reason: the old
declared_upi/expected_upi figures never distinguished which UPI app
was actually used, so this migration cannot honestly attribute them to
PhonePe or Paytm specifically.

See PROJECT_CONTEXT.md's Step 2 entry and
tests/test_reconciliation_migration.py (a pre-migration reconciliation,
built and verified to still read back correctly after this runs).
"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8451c0ddca47'
down_revision: Union[str, Sequence[str], None] = '752fd2af7475'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


tenders_table = sa.table(
    'tenders',
    sa.column('id', sa.String),
    sa.column('created_at', sa.DateTime),
    sa.column('updated_at', sa.DateTime),
    sa.column('status', sa.String),
    sa.column('is_deleted', sa.Boolean),
    sa.column('name', sa.String),
    sa.column('settlement_type', sa.String),
)

shift_reconciliations_table = sa.table(
    'shift_reconciliations',
    sa.column('id', sa.String),
    sa.column('expected_cash', sa.Numeric),
    sa.column('declared_cash', sa.Numeric),
    sa.column('cash_variance', sa.Numeric),
    sa.column('expected_upi', sa.Numeric),
    sa.column('declared_upi', sa.Numeric),
    sa.column('upi_variance', sa.Numeric),
    sa.column('expected_card', sa.Numeric),
    sa.column('declared_card', sa.Numeric),
    sa.column('card_variance', sa.Numeric),
)

shift_reconciliation_lines_table = sa.table(
    'shift_reconciliation_lines',
    sa.column('id', sa.String),
    sa.column('shift_reconciliation_id', sa.String),
    sa.column('tender_id', sa.String),
    sa.column('expected', sa.Numeric),
    sa.column('declared', sa.Numeric),
    sa.column('variance', sa.Numeric),
)


def _ensure_tenders(bind) -> dict:
    existing = {
        row[0]: row[1]
        for row in bind.execute(sa.select(tenders_table.c.name, tenders_table.c.id)).fetchall()
    }
    now = datetime.now(timezone.utc)
    for name, settlement_type in (("Cash", "immediate_cash"), ("Card", "bank_settled"), ("Other", "immediate_cash")):
        if name not in existing:
            new_id = str(uuid.uuid4())
            bind.execute(
                tenders_table.insert().values(
                    id=new_id, created_at=now, updated_at=now, status='active',
                    is_deleted=False, name=name, settlement_type=settlement_type,
                )
            )
            existing[name] = new_id
    return existing


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'shift_reconciliation_lines',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('shift_reconciliation_id', sa.String(length=36), nullable=False),
        sa.Column('tender_id', sa.String(length=36), nullable=False),
        sa.Column('expected', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('declared', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('variance', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['shift_reconciliation_id'], ['shift_reconciliations.id']),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'shift_reconciliation_id', 'tender_id', name='uq_shift_reconciliation_lines_recon_tender'
        ),
    )

    bind = op.get_bind()
    tenders_by_name = _ensure_tenders(bind)
    cash_id, card_id, other_id = tenders_by_name["Cash"], tenders_by_name["Card"], tenders_by_name["Other"]

    rows = bind.execute(
        sa.select(
            shift_reconciliations_table.c.id,
            shift_reconciliations_table.c.expected_cash,
            shift_reconciliations_table.c.declared_cash,
            shift_reconciliations_table.c.cash_variance,
            shift_reconciliations_table.c.expected_upi,
            shift_reconciliations_table.c.declared_upi,
            shift_reconciliations_table.c.upi_variance,
            shift_reconciliations_table.c.expected_card,
            shift_reconciliations_table.c.declared_card,
            shift_reconciliations_table.c.card_variance,
        )
    ).fetchall()

    for (recon_id, exp_cash, dec_cash, var_cash, exp_upi, dec_upi, var_upi, exp_card, dec_card, var_card) in rows:
        bind.execute(
            shift_reconciliation_lines_table.insert(),
            [
                dict(
                    id=str(uuid.uuid4()), shift_reconciliation_id=recon_id, tender_id=cash_id,
                    expected=exp_cash, declared=dec_cash, variance=var_cash,
                ),
                dict(
                    id=str(uuid.uuid4()), shift_reconciliation_id=recon_id, tender_id=other_id,
                    expected=exp_upi, declared=dec_upi, variance=var_upi,
                ),
                dict(
                    id=str(uuid.uuid4()), shift_reconciliation_id=recon_id, tender_id=card_id,
                    expected=exp_card, declared=dec_card, variance=var_card,
                ),
            ],
        )

    with op.batch_alter_table('shift_reconciliations', schema=None) as batch_op:
        batch_op.drop_column('expected_cash')
        batch_op.drop_column('declared_cash')
        batch_op.drop_column('cash_variance')
        batch_op.drop_column('expected_upi')
        batch_op.drop_column('declared_upi')
        batch_op.drop_column('upi_variance')
        batch_op.drop_column('expected_card')
        batch_op.drop_column('declared_card')
        batch_op.drop_column('card_variance')


def downgrade() -> None:
    """Downgrade schema. Re-adds the nine columns and backfills them from
    shift_reconciliation_lines - the Tender rows this migration may have
    created are left in place (other data may reference them by now via
    Sale/Payment/Expense.tender_id; deleting them here would be actively
    harmful, not just unnecessary)."""
    with op.batch_alter_table('shift_reconciliations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expected_cash', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('declared_cash', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('cash_variance', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('expected_upi', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('declared_upi', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('upi_variance', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('expected_card', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('declared_card', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('card_variance', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))

    bind = op.get_bind()
    tenders_by_name = {
        row[0]: row[1] for row in bind.execute(sa.select(tenders_table.c.name, tenders_table.c.id)).fetchall()
    }

    line_rows = bind.execute(
        sa.select(
            shift_reconciliation_lines_table.c.shift_reconciliation_id,
            shift_reconciliation_lines_table.c.tender_id,
            shift_reconciliation_lines_table.c.expected,
            shift_reconciliation_lines_table.c.declared,
            shift_reconciliation_lines_table.c.variance,
        )
    ).fetchall()

    tender_id_to_name = {v: k for k, v in tenders_by_name.items()}
    column_by_tender_name = {
        "Cash": ("expected_cash", "declared_cash", "cash_variance"),
        "Card": ("expected_card", "declared_card", "card_variance"),
        "Other": ("expected_upi", "declared_upi", "upi_variance"),
    }

    for recon_id, tender_id, expected, declared, variance in line_rows:
        name = tender_id_to_name.get(tender_id)
        columns = column_by_tender_name.get(name)
        if not columns:
            continue  # a tender this migration didn't create - nothing to fold back into the old three columns
        expected_col, declared_col, variance_col = columns
        bind.execute(
            shift_reconciliations_table.update()
            .where(shift_reconciliations_table.c.id == recon_id)
            .values(**{expected_col: expected, declared_col: declared, variance_col: variance})
        )

    op.drop_table('shift_reconciliation_lines')
