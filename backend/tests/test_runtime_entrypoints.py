from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app
import main as flask_main
import manage
import mcp_main
import sketch_to_json
from app.common import extensions
from app.common.errors import ApiError


class RuntimeEntrypointTests(unittest.TestCase):
    def test_flask_application_factory_routes_errors_and_cors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = SimpleNamespace(frontend_origins=("http://localhost:8122",))
            with patch.object(app, "ROOT_DIR", root), patch.object(app, "settings", settings), patch.object(app, "initialize_extensions"), patch.object(app, "resume_pending_import_jobs"):
                application = app.create_app()
                @application.get("/api/test-api-error")
                def api_error():
                    raise ApiError("no", 403)
                client = application.test_client()
                missing = client.get("/", headers={"Origin": "http://localhost:8122"})
                self.assertEqual(missing.status_code, 503)
                self.assertEqual(missing.headers["Access-Control-Allow-Origin"], "http://localhost:8122")
                self.assertEqual(client.get("/api/no-route").status_code, 404)
                self.assertEqual(client.get("/api/test-api-error").status_code, 403)
                frontend = root / "canvas-react" / "dist"
                frontend.mkdir(parents=True)
                (frontend / "index.html").write_text("index", encoding="utf-8")
                (frontend / "app.js").write_text("app", encoding="utf-8")
                for path, payload in (("/", b"index"), ("/app.js", b"app"), ("/not-a-file", b"index")):
                    response = client.get(path)
                    self.assertEqual(response.data, payload)
                    response.close()

    def test_extensions_initialization_and_accessors(self) -> None:
        database = Mock()
        redis = Mock()
        minio = Mock()
        minio.bucket_exists.return_value = False
        settings = SimpleNamespace(
            database_dsn="sqlite:///data.db", redis_url="redis://localhost", minio_endpoint="localhost:9000",
            minio_access_key="key", minio_secret_key="secret", minio_bucket="bucket", minio_secure=False,
        )
        previous = extensions.database, extensions.redis_client, extensions.minio_client
        try:
            with patch.object(extensions, "settings", settings), patch.object(extensions, "Database", return_value=database), patch.object(extensions, "Redis", SimpleNamespace(from_url=Mock(return_value=redis))), patch.object(extensions, "Minio", return_value=minio):
                extensions.database = extensions.redis_client = extensions.minio_client = None
                extensions.initialize_extensions()
                self.assertIs(extensions.get_database(), database)
                self.assertIs(extensions.get_redis(), redis)
                self.assertIs(extensions.get_minio(), minio)
            extensions.database = extensions.redis_client = extensions.minio_client = None
            with self.assertRaises(RuntimeError):
                extensions.get_database()
            incomplete = SimpleNamespace(database_dsn="", redis_url="", minio_endpoint="", minio_access_key="", minio_secret_key="", minio_bucket="", minio_secure=False)
            with patch.object(extensions, "settings", incomplete), self.assertRaises(RuntimeError):
                extensions.initialize_extensions()
        finally:
            extensions.database, extensions.redis_client, extensions.minio_client = previous

    def test_command_entrypoints(self) -> None:
        flask_app = Mock()
        with patch.object(sys, "argv", ["main.py", "--host", "0.0.0.0", "--port", "9000"]), patch.object(flask_main, "create_app", return_value=flask_app):
            flask_main.main()
        flask_app.run.assert_called_once_with(host="0.0.0.0", port=9000, debug=False, threaded=True)

        with patch.object(sys, "argv", ["mcp_main.py", "--host", "0.0.0.0", "--port", "9001"]), patch.object(mcp_main, "initialize_extensions"), patch.object(mcp_main, "create_mcp_app", return_value="application"), patch.object(mcp_main.uvicorn, "run") as run:
            mcp_main.main()
        run.assert_called_once_with("application", host="0.0.0.0", port=9001, log_level="info")

        config = Mock()
        with patch.object(manage, "alembic_config", return_value=config), patch.object(manage.command, "upgrade") as upgrade, patch.object(sys, "argv", ["manage.py", "db", "upgrade"]):
            manage.main()
        upgrade.assert_called_once_with(config, "head")
        with patch.object(manage, "alembic_config", return_value=config), patch.object(manage.command, "current") as current, patch.object(sys, "argv", ["manage.py", "db", "current"]):
            manage.main()
        current.assert_called_once_with(config)
        with patch.object(manage, "alembic_config", return_value=config), patch.object(manage.command, "stamp") as stamp, patch.object(sys, "argv", ["manage.py", "db", "stamp", "base"]):
            manage.main()
        stamp.assert_called_once_with(config, "base")
        with patch.object(manage, "alembic_config", return_value=config), patch.object(manage.command, "revision") as revision, patch.object(sys, "argv", ["manage.py", "db", "revision", "-m", "add users"]):
            manage.main()
        revision.assert_called_once_with(config, message="add users")

        source = Mock()
        with patch.object(sys, "argv", ["sketch_to_json.py", "source.sketch", "output"]), patch.object(sketch_to_json, "sketch_to_json", return_value={"zip_path": "archive.zip", "output_path": "output"}) as convert:
            sketch_to_json.main()
        convert.assert_called_once()

    def test_migration_dsn_helpers(self) -> None:
        with patch.object(manage, "settings", SimpleNamespace(database_dsn="sqlite:///data/app.db")), patch.object(manage, "APP_ROOT_DIR", Path("C:/repo")):
            self.assertIn("data/app.db", manage.sqlalchemy_dsn())
        with patch.object(manage, "settings", SimpleNamespace(database_dsn="mysql://user:pass@host/db")):
            self.assertEqual(manage.sqlalchemy_dsn(), "mysql+pymysql://user:pass@host/db")
        with patch.object(manage, "settings", SimpleNamespace(database_dsn="postgresql://host/db")):
            self.assertEqual(manage.sqlalchemy_dsn(), "postgresql://host/db")


if __name__ == "__main__":
    unittest.main()
