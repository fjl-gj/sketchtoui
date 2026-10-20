from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.controllers import auth_controller, mcp_controller, project_controller
from app.controllers.system import health_controller


USER = {
    "id": "user",
    "email": "user@example.com",
    "username": "user",
    "phone": None,
    "email_verified": 1,
    "email_verified_at": "now",
    "status": "active",
    "last_login_at": None,
    "created_at": "created",
}


def application() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(auth_controller.auth_bp)
    app.register_blueprint(mcp_controller.mcp_bp)
    app.register_blueprint(project_controller.projects_bp)
    app.register_blueprint(health_controller.health_bp)
    return app


class ControllerTests(unittest.TestCase):
    def test_authentication_endpoints(self) -> None:
        service = Mock()
        service.register.return_value = (USER, "session")
        service.login.return_value = (USER, "session")
        app = application()
        with patch.object(auth_controller, "service", service), patch.object(auth_controller, "current_user", return_value=USER), patch("app.common.extensions.get_cache", return_value=Mock()):
            client = app.test_client()
            self.assertEqual(client.get("/api/auth/me").get_json()["user"]["id"], "user")
            self.assertEqual(client.post("/api/auth/send-verification", json={"email": "user@example.com"}).status_code, 200)
            registration = client.post("/api/auth/register", json={"email": "user@example.com", "username": "user", "password": "Password1", "code": "123456"})
            login = client.post("/api/auth/login", json={"identity": "user", "password": "Password1"})
            logout = client.post("/api/auth/logout")

        self.assertEqual(registration.status_code, 201)
        self.assertIn("sketch_session", registration.headers["Set-Cookie"])
        self.assertEqual(login.status_code, 200)
        self.assertEqual(logout.get_json(), {"ok": True})
        service.send_registration_verification.assert_called_once()

    def test_mcp_token_endpoints(self) -> None:
        service = Mock()
        service.list_tokens.return_value = [{"id": "token"}]
        service.create_token.return_value = ({"id": "token"}, "skt_secret")
        service.set_enabled.return_value = {"id": "token", "enabled": False}
        app = application()
        with patch.object(mcp_controller, "service", service), patch.object(mcp_controller, "current_user", return_value=USER), patch.object(mcp_controller, "settings", SimpleNamespace(mcp_public_url="https://mcp.example/mcp")):
            client = app.test_client()
            self.assertEqual(client.get("/api/mcp/config").get_json()["url"], "https://mcp.example/mcp")
            self.assertEqual(client.get("/api/mcp/tokens").get_json()["tokens"][0]["id"], "token")
            self.assertEqual(client.post("/api/mcp/tokens", json={"name": "Codex"}).status_code, 201)
            self.assertEqual(client.patch("/api/mcp/tokens/token", json={"enabled": False}).get_json()["token"]["enabled"], False)
            self.assertEqual(client.patch("/api/mcp/tokens/token", json={"enabled": "false"}).status_code, 400)
            self.assertEqual(client.delete("/api/mcp/tokens/token").get_json(), {"ok": True})

    def test_project_endpoints_and_binary_resources(self) -> None:
        service = Mock()
        service.list_projects.return_value = [{"id": "project"}]
        service.queue_import.return_value = {"id": "job"}
        service.queue_reimport.return_value = {"id": "job2"}
        service.list_versions.return_value = [{"id": "version"}]
        service.get_job.return_value = {"id": "job", "status": "running"}
        service.read_object.return_value = (b'{"groups": []}', "application/json")
        app = application()
        with patch.object(project_controller, "service", service), patch.object(project_controller, "current_user", return_value=USER):
            client = app.test_client()
            self.assertEqual(client.get("/api/projects").get_json()["projects"][0]["id"], "project")
            self.assertEqual(client.post("/api/projects", data=b"zip", headers={"X-Filename": "test%20file.sketch", "X-Project-Name": "Test%20Project", "Content-Type": "application/octet-stream"}).status_code, 202)
            self.assertEqual(client.post("/api/projects/project/versions", data=b"zip", headers={"X-Filename": "test.sketch", "Content-Type": "application/octet-stream"}).status_code, 202)
            self.assertEqual(client.get("/api/projects/project/versions").get_json()["versions"][0]["id"], "version")
            self.assertEqual(client.get("/api/imports/job").get_json()["import"]["id"], "job")
            self.assertEqual(client.delete("/api/projects/project").get_json(), {"ok": True})
            self.assertEqual(client.get("/api/projects/project/manifest").get_json(), {"groups": []})
            self.assertEqual(client.get("/api/projects/project/canvas/desktop/canvas.json").status_code, 200)
            self.assertEqual(client.get("/api/projects/project/assets/images/a.png").status_code, 200)
        self.assertEqual(service.queue_import.call_args.args[1:3], ("test file.sketch", "Test Project"))

    def test_health_endpoint(self) -> None:
        app = application()
        with patch.object(health_controller, "settings", SimpleNamespace(database_dsn="sqlite:///data/test.db", cache_backend="redis", storage_backend="minio", minio_bucket="bucket")):
            payload = app.test_client().get("/api/health").get_json()
        self.assertEqual(payload, {"status": "ok", "databaseBackend": "sqlite", "cacheBackend": "redis", "storageBackend": "minio", "minioBucket": "bucket"})


if __name__ == "__main__":
    unittest.main()
