"""Regression test for the riskiest migration in this project
(8451c0ddca47, PROJECT_CONTEXT.md's Step 2): ShiftReconciliation's fixed
cash/upi/card columns reshaped into per-tender ShiftReconciliationLine
rows. Builds a real pre-migration row using raw SQL against the OLD
nine-column schema (upgrading only as far as the migration just before
this one), runs the migration, and proves the reconciliation - and its
exact figures - still reads back correctly afterward. Also proves the
migration is reversible: downgrading restores the original columns
with the original values.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic import command


PRE_MIGRATION_REVISION = "752fd2af7475"  # immediately before the risky one


@pytest.fixture()
def alembic_cfg(tmp_path):
    db_path = tmp_path / "test_reconciliation_migration.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg, str(db_path)


def _seed_pre_migration_reconciliation(db_path: str) -> dict:
    """Inserts one real ShiftReconciliation row shaped exactly like the
    schema looked before this migration existed - nine explicit cash/
    upi/card columns, non-trivial values including a negative variance
    and a non-zero UPI figure, so the test can tell a real value from a
    default/zeroed one."""
    engine = sa.create_engine(f"sqlite:///{db_path}")
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        role_id = "role-1"
        conn.execute(sa.text(
            "INSERT INTO roles (id, name, description, created_at, updated_at, status, is_deleted) "
            "VALUES (:id, 'ADMIN', 'Admin', :now, :now, 'active', 0)"
        ), {"id": role_id, "now": now})
        user_id = "user-1"
        conn.execute(sa.text(
            "INSERT INTO users (id, username, email, password_hash, is_active, is_locked, failed_attempts, "
            "must_change_password, role_id, created_at, updated_at, status, is_deleted) "
            "VALUES (:id, 'admin', 'a@a.com', 'x', 1, 0, 0, 0, :role_id, :now, :now, 'active', 0)"
        ), {"id": user_id, "role_id": role_id, "now": now})
        shift_id = "shift-1"
        conn.execute(sa.text(
            "INSERT INTO shifts (id, shift_date, shift_label, opened_by_id, status, created_at, updated_at, is_deleted) "
            "VALUES (:id, '2026-01-01', 'Morning', :user_id, 'closed', :now, :now, 0)"
        ), {"id": shift_id, "user_id": user_id, "now": now})
        recon_id = "recon-1"
        conn.execute(sa.text(
            "INSERT INTO shift_reconciliations "
            "(id, shift_id, expected_cash, declared_cash, cash_variance, expected_upi, declared_upi, upi_variance, "
            "expected_card, declared_card, card_variance, classification, status, performed_by_id, performed_at) "
            "VALUES (:id, :shift_id, 1000.00, 995.50, -4.50, 500.00, 500.00, 0.00, 200.00, 210.25, 10.25, "
            "'warning', 'accepted', :user_id, :now)"
        ), {"id": recon_id, "shift_id": shift_id, "user_id": user_id, "now": now})
    return {"recon_id": recon_id, "shift_id": shift_id, "user_id": user_id}


def test_pre_migration_reconciliation_reads_back_correctly(alembic_cfg):
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, PRE_MIGRATION_REVISION)
    ids = _seed_pre_migration_reconciliation(db_path)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # The row itself, and its classification/status, survive untouched.
        row = conn.execute(
            sa.text("SELECT classification, status FROM shift_reconciliations WHERE id = :id"),
            {"id": ids["recon_id"]},
        ).fetchone()
        assert row == ("warning", "accepted")

        # Old nine columns are gone.
        columns = {c[1] for c in conn.execute(sa.text("PRAGMA table_info(shift_reconciliations)"))}
        assert "expected_cash" not in columns
        assert "cash_variance" not in columns
        assert "upi_variance" not in columns
        assert "card_variance" not in columns

        # Every figure reappears, exactly, as a line - Cash and Card by
        # their own name, "UPI" folded into "Other" (see the migration's
        # own docstring for why, and PAYMENT_METHOD_TO_TENDER_NAME for
        # the identical reasoning applied elsewhere in this project).
        lines = conn.execute(sa.text(
            "SELECT t.name, l.expected, l.declared, l.variance "
            "FROM shift_reconciliation_lines l JOIN tenders t ON t.id = l.tender_id "
            "WHERE l.shift_reconciliation_id = :id ORDER BY t.name"
        ), {"id": ids["recon_id"]}).fetchall()

        by_name = {r[0]: (Decimal(str(r[1])), Decimal(str(r[2])), Decimal(str(r[3]))) for r in lines}
        assert by_name["Cash"] == (Decimal("1000.00"), Decimal("995.50"), Decimal("-4.50"))
        assert by_name["Other"] == (Decimal("500.00"), Decimal("500.00"), Decimal("0.00"))
        assert by_name["Card"] == (Decimal("200.00"), Decimal("210.25"), Decimal("10.25"))


def test_migration_is_reversible(alembic_cfg):
    """A downgrade must restore the exact original figures, not just
    add the columns back empty - proof the reshape genuinely didn't
    destroy anything, in either direction."""
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, PRE_MIGRATION_REVISION)
    ids = _seed_pre_migration_reconciliation(db_path)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, PRE_MIGRATION_REVISION)

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.execute(sa.text(
            "SELECT expected_cash, declared_cash, cash_variance, expected_upi, declared_upi, upi_variance, "
            "expected_card, declared_card, card_variance FROM shift_reconciliations WHERE id = :id"
        ), {"id": ids["recon_id"]}).fetchone()
        assert [Decimal(str(v)) for v in row] == [
            Decimal("1000.00"), Decimal("995.50"), Decimal("-4.50"),
            Decimal("500.00"), Decimal("500.00"), Decimal("0.00"),
            Decimal("200.00"), Decimal("210.25"), Decimal("10.25"),
        ]

        tables = {t[0] for t in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "shift_reconciliation_lines" not in tables
