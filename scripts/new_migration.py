"""Developer tool: autogenerate a NEW Alembic revision from the models, against a scratch
database built by running every existing migration. Never edits an existing migration.

    python scripts/new_migration.py "add check results"
Review the generated file before committing (autogenerate misses some things).
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command  # noqa: E402

from app.database.migrations import _alembic_config, upgrade_to_head  # noqa: E402


def main(message: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "scratch.db")
        upgrade_to_head(db)
        command.revision(_alembic_config(db), message=message, autogenerate=True)


if __name__ == "__main__":
    main(sys.argv[1])
