"""Guards the whole site-visit build: every new table/column must have a migration.

Builds a database purely from the Alembic migrations and asks Alembic whether the models
would change anything. An empty answer means migrations and models agree.
"""

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.database.base import Base
from app.database.migrations import upgrade_to_head


def test_migrations_produce_exactly_the_model_schema(tmp_path):
    db = tmp_path / "m.db"
    upgrade_to_head(str(db))
    engine = create_engine(f"sqlite:///{db}")
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], diff
