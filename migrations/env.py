from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import ROOT_DIR as APP_ROOT_DIR, settings


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def sqlalchemy_dsn() -> str:
    dsn = settings.database_dsn
    if dsn.startswith("sqlite:///"):
        relative_path = dsn.removeprefix("sqlite:///")
        return f"sqlite:///{(APP_ROOT_DIR / relative_path).resolve().as_posix()}"
    if dsn.startswith("mysql://"):
        return f"mysql+pymysql://{dsn.removeprefix('mysql://')}"
    return dsn


config.set_main_option("sqlalchemy.url", sqlalchemy_dsn())
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection")
    if connectable is None:
        from sqlalchemy import engine_from_config, pool

        connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
