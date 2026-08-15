"""Programmatic wrapper around Alembic (CLAUDE.md: "never modify database
schema without migration"). app/database/connection.py's init_db() calls
upgrade_to_head() instead of Base.metadata.create_all() so every schema
change — including the very first one, which creates all tables — goes
through a real, versioned migration rather than an untracked DDL dump.

The alembic.ini/alembic/ directory location has to be resolved at
runtime rather than assumed relative to the current working directory,
since a PyInstaller onefile build extracts to a fresh temp directory
(sys._MEIPASS) on every launch — same reasoning as
connection.py's _default_database_path().
"""

import os
import sys
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine


def _project_root() -> str:
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _alembic_config(db_path: str) -> Config:
    root = _project_root()
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def current_revision(db_path: str) -> Optional[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def head_revision(db_path: str) -> Optional[str]:
    script = ScriptDirectory.from_config(_alembic_config(db_path))
    return script.get_current_head()


def has_pending_migrations(db_path: str) -> bool:
    return current_revision(db_path) != head_revision(db_path)


def upgrade_to_head(db_path: str) -> None:
    command.upgrade(_alembic_config(db_path), "head")
