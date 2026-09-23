"""add shift_id to attendance

Revision ID: 9f3c7a1b2d4e
Revises: c4a1e5f9d3b2
Create Date: 2026-09-23 01:00:00.000000

Attendance.shift_label was free text (e.g. "Morning") because the Shift
entity didn't exist yet when Attendance was built (Phase 6); Shift exists
now (Phase 7), so this adds a real shift_id foreign key and backfills what
it safely can from existing data.

shift_label is intentionally left in place, not dropped - it is historical
free text, and not every attendance row can be safely matched to a real
Shift row (some predate this migration's matching rules, some days have no
Shift record at all). Dropping it would silently lose that history; per
project rules, historical data is never removed, only added to.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f3c7a1b2d4e'
down_revision: Union[str, Sequence[str], None] = 'c4a1e5f9d3b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('attendance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shift_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_attendance_shift_id_shifts', 'shifts', ['shift_id'], ['id'])
        batch_op.create_index(batch_op.f('ix_attendance_shift_id'), ['shift_id'])

    _backfill_shift_id(op.get_bind())


def _backfill_shift_id(conn) -> None:
    """For each attendance row, look for Shift rows on the same date.
    Prefer an exact shift_label match when more than one shift exists
    that day (e.g. "Morning" vs "Evening"); otherwise, if there is
    exactly one shift that day, use it unambiguously. A row that still
    can't be resolved (no shift recorded for that date, or more than one
    shift that day with no label match) is left with shift_id NULL -
    never guessed at - and its original shift_label text is untouched.
    """
    attendance_rows = conn.execute(sa.text("SELECT id, attendance_date, shift_label FROM attendance")).fetchall()

    matched_by_label = 0
    matched_by_sole_shift = 0
    unmatched = 0

    for row in attendance_rows:
        shifts_that_day = conn.execute(
            sa.text("SELECT id, shift_label FROM shifts WHERE shift_date = :d"),
            {"d": row.attendance_date},
        ).fetchall()

        target_shift_id = None
        if row.shift_label:
            label_matches = [
                s for s in shifts_that_day if (s.shift_label or "").strip().lower() == row.shift_label.strip().lower()
            ]
            if len(label_matches) == 1:
                target_shift_id = label_matches[0].id
                matched_by_label += 1

        if target_shift_id is None and len(shifts_that_day) == 1:
            target_shift_id = shifts_that_day[0].id
            matched_by_sole_shift += 1

        if target_shift_id is not None:
            conn.execute(sa.text("UPDATE attendance SET shift_id = :sid WHERE id = :aid"), {"sid": target_shift_id, "aid": row.id})
        else:
            unmatched += 1

    print(
        f"[migration 9f3c7a1b2d4e] attendance.shift_id backfill over {len(attendance_rows)} row(s): "
        f"{matched_by_label} matched by exact same-day label, {matched_by_sole_shift} matched as the sole shift "
        f"that day, {unmatched} left unmatched (shift_label preserved on every row either way)."
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('attendance', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attendance_shift_id'))
        batch_op.drop_constraint('fk_attendance_shift_id_shifts', type_='foreignkey')
        batch_op.drop_column('shift_id')
