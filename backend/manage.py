from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import ROOT_DIR as APP_ROOT_DIR, settings


def sqlalchemy_dsn() -> str:
    dsn = settings.database_dsn
    if dsn.startswith("sqlite:///"):
        relative_path = dsn.removeprefix("sqlite:///")
        return f"sqlite:///{(APP_ROOT_DIR / relative_path).resolve().as_posix()}"
    if dsn.startswith("mysql://"):
        return f"mysql+pymysql://{dsn.removeprefix('mysql://')}"
    return dsn


def alembic_config() -> Config:
    config = Config(str(ROOT_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", sqlalchemy_dsn())
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="SketchToUI database migration manager.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    database = subparsers.add_parser("db", help="Manage Alembic migrations.")
    database_subparsers = database.add_subparsers(dest="database_command", required=True)
    database_subparsers.add_parser("upgrade", help="Upgrade schema to the latest migration.")
    database_subparsers.add_parser("current", help="Show the current migration revision.")
    stamp = database_subparsers.add_parser("stamp", help="Mark an existing schema at a revision without changing it.")
    stamp.add_argument("revision", nargs="?", default="head")
    revision = database_subparsers.add_parser("revision", help="Create a new empty migration file.")
    revision.add_argument("-m", "--message", required=True)
    args = parser.parse_args()
    config = alembic_config()
    if args.database_command == "upgrade":
        command.upgrade(config, "head")
    elif args.database_command == "current":
        command.current(config)
    elif args.database_command == "stamp":
        command.stamp(config, args.revision)
    else:
        command.revision(config, message=args.message)


if __name__ == "__main__":
    main()
