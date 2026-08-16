from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import all models so Base.metadata is fully populated before autogenerate
# compares it against the database (mirrors app/database/connection.py).
import app.models  # noqa: F401
from app.database.base import Base
from app.database.connection import get_database_path

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers defaults to True, which silently disables
    # every logger that already exists and isn't named in alembic.ini's
    # own [loggers] section - including the app's own "petrol_pump_erp"
    # logger (app/core/logging.py), for the rest of the process. Since
    # init_db() runs migrations on every startup, that would kill all
    # application logging right after the first launch.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# app/database/migrations.py sets sqlalchemy.url explicitly before
# running migrations programmatically (so it targets whatever exact
# path the caller means - including a test's monkeypatched path - not
# necessarily the "real" default). Only fall back to computing it here
# when nothing already overrode the ini's placeholder, e.g. when running
# `alembic` directly from the CLI rather than through that wrapper.
_PLACEHOLDER_URL = "driver://user:pass@localhost/dbname"
if config.get_main_option("sqlalchemy.url") in (None, _PLACEHOLDER_URL):
    config.set_main_option("sqlalchemy.url", f"sqlite:///{get_database_path()}")

target_metadata = Base.metadata

# SQLite can't ALTER a column's type or DROP a column in place; Alembic's
# "batch mode" works around this by rebuilding the table under the hood.
# Every migration in this project targets SQLite, so this is on globally
# rather than per-migration.
RENDER_AS_BATCH = True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=RENDER_AS_BATCH,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=RENDER_AS_BATCH,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
