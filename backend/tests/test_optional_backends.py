from __future__ import annotations

import importlib
import io
import os
import runpy
import sys
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from alembic import command
from alembic.config import Config
from minio.error import S3Error


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "backend"))

import app
from app.common import cache as cache_module, extensions
from app.common.cache import MemoryCache
from app.common.storage import LocalStorage, MinioStorage
from app.controllers.system import health_controller
from app.mcp.rate_limit import McpRateLimitMiddleware
from app.services import auth_service, project_import_service
from app.services.mcp_design_service import McpDesignService
from app.services.mcp_token_service import McpTokenService
from test_legacy_tools import make_sketch


config_module = importlib.import_module("app.config.settings")


class OptionalBackendTests(unittest.TestCase):
    def test_backend_selection_defaults_legacy_configuration_and_explicit_override(self) -> None:
        cases = (
            ({}, ("memory", "local")),
            ({"REDIS_URL": "redis://localhost", "MINIO_ENDPOINT": "localhost:9000"}, ("redis", "minio")),
            ({"REDIS_URL": "redis://localhost", "MINIO_ENDPOINT": "localhost:9000", "CACHE_BACKEND": "memory", "STORAGE_BACKEND": "local"}, ("memory", "local")),
        )
        for environment, expected in cases:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True), patch.object(Path, "is_file", return_value=False):
                settings = runpy.run_path(str(ROOT_DIR / "backend/app/config/settings.py"))["settings"]
                self.assertEqual((settings.cache_backend, settings.storage_backend), expected)

    def test_cache_expiration_cooldown_and_cleanup(self) -> None:
        cache = MemoryCache()
        with patch.object(cache_module.time, "monotonic", return_value=100):
            self.assertTrue(cache.set("code", "123456", nx=True, ex=60))
            self.assertFalse(cache.set("code", "other", nx=True, ex=60))
            self.assertEqual(cache.ttl("code"), 60)
            cache.set("persistent", "value")
            self.assertEqual(cache.ttl("persistent"), -1)
        with patch.object(cache_module.time, "monotonic", return_value=161):
            self.assertIsNone(cache.get("code"))
            self.assertEqual(cache.ttl("code"), -2)
            self.assertTrue(cache.set("code", "new", nx=True, ex=60))
            self.assertEqual(cache.delete("code", "persistent", "missing"), 2)
            cache.set("expired", "value", ex=1)
        with patch.object(cache_module.time, "monotonic", return_value=222):
            cache.set("session", "user", ex=60)
            self.assertNotIn("expired", cache._values)
            cache.set("session", "replacement")
            self.assertEqual(cache.ttl("session"), -1)

    def test_cache_pipeline_is_atomic_across_threads_and_rate_limits_expire(self) -> None:
        cache = MemoryCache()
        def increment(_index: int) -> int:
            return cache.pipeline().incr("requests").expire("requests", 60).execute()[0]
        with ThreadPoolExecutor(max_workers=8) as workers:
            counts = list(workers.map(increment, range(100)))
        self.assertEqual(sorted(counts), list(range(1, 101)))
        limiter = McpRateLimitMiddleware(Mock(), "/mcp", per_token_limit=2, global_limit=3)
        with patch("app.mcp.rate_limit.get_cache", return_value=cache), patch("app.mcp.rate_limit.time.time", return_value=120), patch.object(cache_module.time, "monotonic", return_value=1000):
            self.assertTrue(limiter.consume("Bearer first")[0])
            self.assertTrue(limiter.consume("Bearer first")[0])
            self.assertFalse(limiter.consume("Bearer first")[0])
            self.assertFalse(limiter.consume("Bearer second")[0])
        with patch("app.mcp.rate_limit.get_cache", return_value=cache), patch("app.mcp.rate_limit.time.time", return_value=180), patch.object(cache_module.time, "monotonic", return_value=1062):
            self.assertTrue(limiter.consume("Bearer first")[0])

    def test_local_storage_persistence_missing_paths_and_scoped_deletion(self) -> None:
        with tempfile.TemporaryDirectory(prefix=".tmp_optional_storage_", dir=ROOT_DIR) as directory:
            root = Path(directory)
            storage = LocalStorage(root / "storage")
            source = root / "source.png"
            source.write_bytes(b"image")
            storage.put_file("users/one/project/icon.png", source)
            storage.put_file("users/one/project-other/icon.png", source)
            self.assertEqual(LocalStorage(storage.root).read_object("users/one/project/icon.png"), (b"image", "image/png"))
            with self.assertRaises(FileNotFoundError):
                storage.read_object("users/one/project")
            for unsafe in ("", ".", "..", "../outside", "/absolute", "C:/outside", "folder\\file", "folder/../../outside"):
                for operation in (storage.read_object, storage.delete_prefix):
                    with self.subTest(path=unsafe, operation=operation.__name__), self.assertRaises(ValueError):
                        operation(unsafe)
                with self.assertRaises(ValueError):
                    storage.put_file(unsafe, source)
            storage.delete_prefix("users/one/project")
            storage.delete_prefix("users/one/project")
            with self.assertRaises(FileNotFoundError):
                storage.read_object("users/one/project/icon.png")
            self.assertEqual(storage.read_object("users/one/project-other/icon.png")[0], b"image")
            self.assertEqual(list(storage.root.rglob(".upload-*")), [])

    def test_minio_adapter_preserves_content_type_and_closes_responses(self) -> None:
        client = Mock()
        client.bucket_exists.return_value = True
        response = Mock(headers={"Content-Type": "image/png"})
        response.read.return_value = b"image"
        client.get_object.return_value = response
        storage = MinioStorage(client, "bucket")
        storage.put_file("icon.png", Path("source.png"))
        client.fput_object.assert_called_once_with("bucket", "icon.png", "source.png", content_type="image/png")
        self.assertEqual(storage.read_object("icon.png"), (b"image", "image/png"))
        response.close.assert_called_once()
        response.release_conn.assert_called_once()
        response.read.side_effect = OSError("read failed")
        with self.assertRaises(OSError):
            storage.read_object("icon.png")
        self.assertEqual(response.release_conn.call_count, 2)
        client.get_object.side_effect = S3Error(response=None, code="NoSuchKey", message="missing", resource="object", request_id="request", host_id="host")
        with self.assertRaises(FileNotFoundError):
            storage.read_object("missing.png")
        client.get_object.side_effect = S3Error(response=None, code="AccessDenied", message="denied", resource="object", request_id="request", host_id="host")
        with self.assertRaises(S3Error):
            storage.read_object("private.png")
        client.list_objects.return_value = [SimpleNamespace(object_name="prefix/file")]
        storage.delete_prefix("prefix")
        client.list_objects.assert_called_once_with("bucket", prefix="prefix/", recursive=True)
        client.remove_object.assert_called_once_with("bucket", "prefix/file")

    def test_invalid_backend_configuration_fails_before_connecting(self) -> None:
        settings = replace(config_module.settings, database_dsn="sqlite:///test.db", cache_backend="memory", storage_backend="local")
        for overrides in ({"cache_backend": "unknown"}, {"storage_backend": "unknown"}, {"cache_backend": "redis", "redis_url": ""}, {"storage_backend": "minio", "minio_endpoint": ""}, {"local_storage_dir": ""}):
            with self.subTest(overrides=overrides), patch.object(extensions, "settings", replace(settings, **overrides)), patch.object(extensions, "Database") as database:
                with self.assertRaises(RuntimeError):
                    extensions.initialize_extensions()
                database.assert_not_called()

    def test_registration_import_mcp_read_and_restart_without_external_services(self) -> None:
        with tempfile.TemporaryDirectory(prefix=".tmp_optional_backends_", dir=ROOT_DIR) as directory, ExitStack() as stack:
            root = Path(directory)
            settings = replace(config_module.settings, database_dsn="sqlite:///test.db", cache_backend="memory", storage_backend="local", local_storage_dir="storage", email_delivery="console")
            for module in (config_module, app, extensions, auth_service, project_import_service, health_controller):
                stack.enter_context(patch.object(module, "settings", settings))
            for module in (config_module, extensions):
                stack.enter_context(patch.object(module, "ROOT_DIR", root))
            for name in ("database", "cache_client", "storage_client"):
                stack.enter_context(patch.object(extensions, name, None))
            stack.enter_context(patch.object(project_import_service, "TEMP_DIR", root / "tmp"))
            stack.enter_context(patch.object(extensions.Redis, "from_url", side_effect=AssertionError("Redis must not be used")))
            stack.enter_context(patch.object(extensions, "Minio", side_effect=AssertionError("MinIO must not be used")))
            submitted = stack.enter_context(patch.object(project_import_service, "submit_import_job"))
            config = Config()
            config.set_main_option("script_location", str(ROOT_DIR / "migrations"))
            command.upgrade(config, "head")
            application = app.create_app()
            client = application.test_client()
            self.assertEqual(client.get("/api/health").get_json(), {"status": "ok", "databaseBackend": "sqlite", "cacheBackend": "memory", "storageBackend": "local"})
            registration = {"email": "local@example.com", "username": "local", "password": "test-only-password", "code": "123456"}
            login = {"identity": registration["email"], "password": registration["password"]}
            with patch.object(auth_service.secrets, "randbelow", return_value=123456), redirect_stdout(io.StringIO()):
                self.assertEqual(client.post("/api/auth/send-verification", json=registration).status_code, 200)
            self.assertEqual(client.post("/api/auth/send-verification", json=registration).status_code, 429)
            registered = client.post("/api/auth/register", json=registration)
            self.assertEqual(registered.status_code, 201, registered.get_json())
            user_id = registered.get_json()["user"]["id"]
            self.assertEqual(client.get("/api/auth/me").status_code, 200)
            client.post("/api/auth/logout")
            self.assertEqual(client.get("/api/auth/me").status_code, 401)
            self.assertEqual(client.post("/api/auth/login", json=login).status_code, 200)
            sketch = root / "fixture"
            make_sketch(sketch)
            archive_bytes = io.BytesIO()
            with zipfile.ZipFile(archive_bytes, "w") as archive:
                for file in sketch.rglob("*"):
                    if file.is_file():
                        archive.write(file, file.relative_to(sketch).as_posix())
            response = client.post("/api/projects", data=archive_bytes.getvalue(), headers={"X-Filename": "test.sketch", "Content-Type": "application/octet-stream"})
            self.assertEqual(response.status_code, 202, response.get_json())
            job_id = response.get_json()["import"]["id"]
            submitted.assert_called_once_with(job_id)
            project_import_service.run_import_job(job_id)
            job = client.get(f"/api/imports/{job_id}").get_json()["import"]
            self.assertEqual(job["stage"], "complete", job)
            project_id = job["project"]["id"]
            manifest = client.get(f"/api/projects/{project_id}/manifest")
            self.assertEqual(manifest.status_code, 200)
            self.assertTrue(manifest.get_json()["groups"])
            asset = client.get(f"/api/projects/{project_id}/assets/images/icon.png")
            self.assertEqual((asset.status_code, asset.data, asset.mimetype), (200, b"image", "image/png"))
            self.assertEqual(client.get(f"/api/projects/{project_id}/assets/missing.png").status_code, 404)
            self.assertEqual(McpDesignService().manifest(user_id, project_id), manifest.get_json())
            _metadata, token = McpTokenService().create_token(user_id, "local")
            # A new app process loses sessions, but the database, tokens and files survive.
            extensions.initialize_extensions()
            self.assertEqual(client.get("/api/auth/me").status_code, 401)
            self.assertEqual(McpTokenService().authenticate(token)["user_id"], user_id)
            self.assertEqual(McpDesignService().manifest(user_id, project_id), manifest.get_json())
            self.assertEqual(project_import_service.get_job(job_id)["stage"], "complete")
            self.assertEqual(client.post("/api/auth/login", json=login).status_code, 200)
            self.assertEqual(client.delete(f"/api/projects/{project_id}").status_code, 200)
            self.assertFalse((root / "storage" / "users" / user_id / "projects" / project_id).exists())


if __name__ == "__main__":
    unittest.main()
