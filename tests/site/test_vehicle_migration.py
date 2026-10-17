"""The vehicle moves out of remarks into sales.vehicle_number (upper case, no spaces); old credit bill details are carried over."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

MIGRATION = next((Path(__file__).resolve().parents[2] / "alembic" / "versions").glob("*06f77403bccb*.py"))


def test_the_vehicle_moves_out_of_remarks_and_into_its_own_column():
    spec = importlib.util.spec_from_file_location("vehicle_migration", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE sales (id TEXT PRIMARY KEY, remarks TEXT, vehicle_number TEXT)"))
        c.execute(sa.text("CREATE TABLE credit_bill_details (sale_id TEXT, vehicle_no TEXT)"))
        for i, remarks in enumerate(["Vehicle: mh 12 ab 1234 - paid by driver", "Vehicle: MH14-XY-1", "just a note", None, None], start=1):
            c.execute(sa.text("INSERT INTO sales (id, remarks) VALUES (:i, :r)"), {"i": f"s{i}", "r": remarks})
        c.execute(sa.text("INSERT INTO credit_bill_details VALUES ('s4', ' mh 31 zz 9 ')"))
        c.execute(sa.text("INSERT INTO credit_bill_details VALUES ('s1', 'OTHER')"))  # the sale's own text wins
        mod.move_vehicle_out_of_remarks(c)
        got = {r[0]: (r[1], r[2]) for r in c.execute(sa.text("SELECT id, vehicle_number, remarks FROM sales"))}
    assert got["s1"] == ("MH12AB1234", "paid by driver")
    assert got["s2"] == ("MH14-XY-1", None)
    assert got["s3"] == (None, "just a note")
    assert got["s4"] == ("MH31ZZ9", None)
    assert got["s5"] == (None, None)
