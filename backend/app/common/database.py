from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


class Database:
    def __init__(self, database_dsn: str, root_dir: Path) -> None:
        self.backend, self.config = self.parse_dsn(database_dsn, root_dir)

    @staticmethod
    def parse_dsn(database_dsn: str, root_dir: Path) -> tuple[str, dict[str, Any]]:
        parsed = urlparse(database_dsn)
        if parsed.scheme in {"mysql", "mysql+pymysql"}:
            database_name = parsed.path.removeprefix("/")
            if not parsed.hostname or not database_name:
                raise ValueError("DATABASE_DSN 的 MySQL 格式必须为 mysql://user:password@host:3306/database")
            return "mysql", {
                "host": parsed.hostname,
                "port": parsed.port or 3306,
                "user": unquote(parsed.username or ""),
                "password": unquote(parsed.password or ""),
                "database": database_name,
            }
        if parsed.scheme == "sqlite":
            relative_path = unquote(parsed.path).lstrip("/")
            if not relative_path:
                raise ValueError("DATABASE_DSN 的 SQLite 格式必须为 sqlite:///data/workspace/sketch.db")
            path = (root_dir / relative_path).resolve()
            if root_dir.resolve() not in path.parents:
                raise ValueError("SQLite 数据库必须保存于项目目录内")
            return "sqlite", {"database": str(path)}
        raise ValueError("DATABASE_DSN 仅支持 sqlite:///... 或 mysql://...")

    def connect(self) -> Any:
        if self.backend == "sqlite":
            path = Path(self.config["database"])
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            return connection
        try:
            import pymysql
        except ImportError as error:
            raise RuntimeError("MySQL 模式需要安装 pymysql：pip install -r requirements.txt") from error
        return pymysql.connect(cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4", autocommit=False, **self.config)

    def adapt(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.backend == "mysql" else sql

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        connection = self.connect()
        cursor = connection.cursor()
        try:
            cursor.execute(self.adapt(sql), tuple(params))
            connection.commit()
            return cursor.rowcount
        finally:
            cursor.close()
            connection.close()

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        connection = self.connect()
        cursor = connection.cursor()
        try:
            cursor.execute(self.adapt(sql), tuple(params))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            cursor.close()
            connection.close()

    def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        connection = self.connect()
        cursor = connection.cursor()
        try:
            cursor.execute(self.adapt(sql), tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()
            connection.close()

    def initialize(self) -> None:
        required = ["users", "projects", "project_versions", "import_jobs", "mcp_tokens", "alembic_version"]
        missing = [table for table in required if not self.has_table(table)]
        if missing:
            raise RuntimeError(
                "数据库尚未完成 Alembic 初始化（缺少："
                + ", ".join(missing)
                + "）。请先运行：python .\\backend\\manage.py db upgrade"
            )

    def has_table(self, table: str) -> bool:
        if self.backend == "sqlite":
            return self.one("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)) is not None
        return self.one("SHOW TABLES LIKE ?", (table,)) is not None
