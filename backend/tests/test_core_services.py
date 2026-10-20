from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask, request
from starlette.requests import Request
from starlette.responses import JSONResponse


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.common.database import Database
from app.common.errors import ApiError
from app.mcp import rate_limit as rate_module
from app.mcp.rate_limit import McpRateLimitMiddleware
from app.services import auth_service as auth_module
from app.services import mcp_token_service as token_module
from app.services.auth_service import AuthService, apply_session_cookie, code_hash, current_user, hash_password, issue_session, verify_password, verify_registration_code
from app.services.mcp_token_service import McpTokenService, public_token, token_hash


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def delete(self, *keys: str) -> int:
        for key in keys:
            self.values.pop(key, None)
            self.expirations.pop(key, None)
        return len(keys)

    def ttl(self, key: str) -> int:
        return self.expirations.get(key, -1)

    def pipeline(self):
        return MemoryPipeline(self)


class MemoryPipeline:
    def __init__(self, redis: MemoryRedis) -> None:
        self.redis = redis
        self.operations: list[tuple[str, tuple]] = []

    def incr(self, key: str) -> None:
        self.operations.append(("incr", (key,)))

    def expire(self, key: str, seconds: int) -> None:
        self.operations.append(("expire", (key, seconds)))

    def execute(self) -> list[int | bool]:
        results: list[int | bool] = []
        for name, arguments in self.operations:
            if name == "incr":
                key = arguments[0]
                value = int(self.redis.values.get(key, "0")) + 1
                self.redis.values[key] = str(value)
                results.append(value)
            else:
                self.redis.expirations[arguments[0]] = arguments[1]
                results.append(True)
        return results


class CoreServiceTests(unittest.TestCase):
    def test_database_sqlite_mysql_and_table_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = Database("sqlite:///data/test.sqlite", root)
            database.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
            database.execute("INSERT INTO items (name) VALUES (?)", ("one",))
            self.assertEqual(database.one("SELECT name FROM items WHERE id = ?", (1,))["name"], "one")
            self.assertEqual(len(database.all("SELECT * FROM items")), 1)
            self.assertTrue(database.has_table("items"))
            with self.assertRaises(RuntimeError):
                database.initialize()
            self.assertEqual(Database("mysql://user:secret@host:3307/design", root).config["port"], 3307)
            with self.assertRaises(ValueError):
                Database("sqlite:///../outside.sqlite", root)
            with self.assertRaises(ValueError):
                Database("postgres://host/database", root)

    def test_auth_helpers_registration_login_and_current_user(self) -> None:
        redis = MemoryRedis()
        user = {"id": "user", "email": "user@example.com", "username": "user", "phone": None, "password_hash": hash_password("Password1"), "email_verified": 1, "email_verified_at": "now", "status": "active", "last_login_at": None, "created_at": "created", "updated_at": "updated"}
        database = Mock()
        database.one.side_effect = [None, user]
        with patch.object(auth_module, "get_database", return_value=database), patch.object(auth_module, "get_redis", return_value=redis), patch.object(auth_module, "verify_registration_code") as verify_code, patch.object(auth_module, "issue_session", return_value="session"):
            registered, session = AuthService().register({"email": "NEW@example.com", "username": "new_user", "password": "Password1", "code": "123456"})
            logged_in, logged_session = AuthService().login({"identity": "user@example.com", "password": "Password1"})

        self.assertEqual(registered["email"], "new@example.com")
        self.assertEqual(session, "session")
        verify_code.assert_called_once()
        self.assertEqual(logged_in["id"], "user")
        self.assertEqual(logged_session, "session")
        self.assertTrue(verify_password("Password1", user["password_hash"]))
        self.assertFalse(verify_password("wrong", user["password_hash"]))
        self.assertEqual(code_hash("123456"), code_hash("123456"))
        with self.assertRaises(ApiError):
            AuthService().register({"email": "bad", "username": "a", "password": "short", "code": "000000"})

        redis.set(auth_module.session_key("session"), "user", ex=10)
        with Flask(__name__).test_request_context("/", headers={"Cookie": f"{auth_module.SESSION_COOKIE}=session"}):
            with patch.object(auth_module, "get_database", return_value=SimpleNamespace(one=lambda *_args: user)), patch.object(auth_module, "get_redis", return_value=redis):
                self.assertEqual(current_user(request, require_verified=True)["id"], "user")
        response = apply_session_cookie(Flask(__name__).response_class(), "session", 10)
        self.assertIn(auth_module.SESSION_COOKIE, response.headers["Set-Cookie"])
        with patch.object(auth_module, "get_redis", return_value=redis):
            self.assertTrue(issue_session("user"))

    def test_verification_code_success_failure_and_cooldown(self) -> None:
        redis = MemoryRedis()
        email = "user@example.com"
        redis.set(auth_module.verification_key(email), json.dumps({"hash": code_hash("123456"), "attempts": 0}), ex=30)
        with patch.object(auth_module, "get_redis", return_value=redis):
            verify_registration_code(email, "123456")
            self.assertIsNone(redis.get(auth_module.verification_key(email)))
            with self.assertRaises(ApiError):
                verify_registration_code(email, "abc")
            redis.set(auth_module.verification_key(email), json.dumps({"hash": code_hash("123456"), "attempts": 0}), ex=30)
            with self.assertRaises(ApiError):
                verify_registration_code(email, "000000")
        with patch.object(auth_module, "get_redis", return_value=redis), patch.object(auth_module, "settings", SimpleNamespace(email_delivery="console")):
            auth_module.send_verification_email(email, "user")
            with self.assertRaises(ApiError):
                auth_module.send_verification_email(email, "user")

    def test_auth_error_paths_and_smtp_delivery(self) -> None:
        with self.assertRaises(ApiError):
            auth_module.validate_email_and_username({"email": "invalid", "username": "valid_name"})
        with self.assertRaises(ApiError):
            auth_module.validate_email_and_username({"email": "user@example.com", "username": "!"})

        redis = MemoryRedis()
        email = "user@example.com"
        redis.set(auth_module.verification_key(email), json.dumps({"hash": code_hash("123456"), "attempts": auth_module.MAX_VERIFY_ATTEMPTS}), ex=10)
        with patch.object(auth_module, "get_redis", return_value=redis), self.assertRaises(ApiError):
            verify_registration_code(email, "123456")

        missing_smtp = SimpleNamespace(email_delivery="smtp", smtp_host="", smtp_sender="", smtp_use_ssl=False)
        with patch.object(auth_module, "get_redis", return_value=MemoryRedis()), patch.object(auth_module, "settings", missing_smtp), self.assertRaises(ApiError):
            auth_module.send_verification_email(email, "user")

        smtp_client = Mock()
        smtp_client.__enter__ = Mock(return_value=smtp_client)
        smtp_client.__exit__ = Mock(return_value=False)
        smtp_settings = SimpleNamespace(
            email_delivery="smtp", smtp_host="smtp.example.com", smtp_sender="noreply@example.com", smtp_use_ssl=False,
            smtp_use_tls=True, smtp_username="user", smtp_password="secret", smtp_port=587,
        )
        with patch.object(auth_module, "get_redis", return_value=MemoryRedis()), patch.object(auth_module, "settings", smtp_settings), patch.object(auth_module.smtplib, "SMTP", return_value=smtp_client):
            auth_module.send_verification_email(email, "user")
        smtp_client.starttls.assert_called_once()
        smtp_client.login.assert_called_once_with("user", "secret")
        smtp_client.send_message.assert_called_once()

        error_redis = MemoryRedis()
        with patch.object(auth_module, "get_redis", return_value=error_redis), patch.object(auth_module, "settings", smtp_settings), patch.object(auth_module.smtplib, "SMTP", side_effect=OSError("offline")), self.assertRaises(ApiError):
            auth_module.send_verification_email(email, "user")

        disabled_user = {"id": "user", "email": email, "username": "user", "email_verified": 0, "status": "disabled", "created_at": "created"}
        redis = MemoryRedis()
        redis.set(auth_module.session_key("session"), "user", ex=10)
        with Flask(__name__).test_request_context("/", headers={"Cookie": f"{auth_module.SESSION_COOKIE}=session"}):
            with patch.object(auth_module, "get_database", return_value=SimpleNamespace(one=lambda *_args: disabled_user)), patch.object(auth_module, "get_redis", return_value=redis), self.assertRaises(ApiError):
                current_user(request)

        database = Mock()
        database.one.return_value = {"id": "taken"}
        with patch.object(auth_module, "get_database", return_value=database), self.assertRaises(ApiError):
            AuthService().send_registration_verification({"email": email, "username": "user"})

    def test_mcp_tokens_and_rate_limit(self) -> None:
        record = {"id": "token", "name": "Token", "token_prefix": "skt_prefix", "scopes_json": json.dumps(["design:read"]), "created_at": "created", "last_used_at": None, "expires_at": None, "enabled": 1}
        database = Mock()
        database.all.return_value = [record.copy()]
        database.one.side_effect = [record.copy(), {"id": "token"}, {"id": "token", "user_id": "user", "name": "Token", "scopes_json": json.dumps(["design:read"]), "username": "user", "email_verified": 1, "status": "active"}]
        with patch.object(token_module, "get_database", return_value=database):
            service = McpTokenService()
            self.assertEqual(service.list_tokens("user")[0]["enabled"], True)
            created, secret = service.create_token("user", "")
            self.assertTrue(secret.startswith("skt_"))
            self.assertEqual(created["name"], "Codex Remote MCP")
            self.assertFalse(service.set_enabled("user", "token", False)["enabled"])
            service.revoke_token("user", "token")
            authenticated = service.authenticate(secret)
        self.assertEqual(authenticated["scopes"], ["design:read"])
        self.assertEqual(token_hash("abc"), token_hash("abc"))
        self.assertEqual(public_token(record)["id"], "token")
        with self.assertRaises(ApiError):
            McpTokenService().create_token("user", "x" * 121)

        redis = MemoryRedis()
        middleware = McpRateLimitMiddleware(lambda _scope, _receive, _send: None, "/mcp", 1, 2)
        with patch.object(rate_module, "get_redis", return_value=redis):
            self.assertTrue(middleware.consume("Bearer abc")[0])
            self.assertFalse(middleware.consume("Bearer abc")[0])
            request = Request({"type": "http", "method": "GET", "path": "/other", "headers": [], "scheme": "http", "server": ("test", 80), "client": ("test", 1), "query_string": b""})
            response = asyncio.run(middleware.dispatch(request, lambda _request: self.async_response()))
        self.assertEqual(response.status_code, 200)

    @staticmethod
    async def async_response() -> JSONResponse:
        return JSONResponse({"ok": True})


if __name__ == "__main__":
    unittest.main()
