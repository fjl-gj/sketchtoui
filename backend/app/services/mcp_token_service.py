from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from typing import Any

from ..common.errors import ApiError
from ..common.extensions import get_database
from .auth_service import iso_now


DEFAULT_SCOPES = ["design:read", "projects:read"]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_token(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "name": record["name"],
        "tokenPrefix": record["token_prefix"],
        "scopes": json.loads(record["scopes_json"]),
        "createdAt": record["created_at"],
        "lastUsedAt": record.get("last_used_at"),
        "expiresAt": record.get("expires_at"),
        "enabled": bool(record.get("enabled", 1)),
    }


class McpTokenService:
    def list_tokens(self, user_id: str) -> list[dict[str, Any]]:
        records = get_database().all(
            "SELECT id, name, token_prefix, scopes_json, created_at, last_used_at, expires_at, enabled FROM mcp_tokens WHERE user_id = ? AND revoked_at IS NULL ORDER BY created_at DESC",
            (user_id,),
        )
        return [public_token(record) for record in records]

    def create_token(self, user_id: str, name: str) -> tuple[dict[str, Any], str]:
        label = name.strip() or "Codex Remote MCP"
        if len(label) > 120:
            raise ApiError("MCP Token 名称不能超过 120 个字符")
        token = f"skt_{secrets.token_urlsafe(32)}"
        record = {
            "id": uuid.uuid4().hex,
            "user_id": user_id,
            "name": label,
            "token_prefix": token[:16],
            "token_hash": token_hash(token),
            "scopes_json": json.dumps(DEFAULT_SCOPES),
            "created_at": iso_now(),
            "enabled": 1,
        }
        get_database().execute(
            "INSERT INTO mcp_tokens (id, user_id, name, token_prefix, token_hash, scopes_json, created_at, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record["id"],
                record["user_id"],
                record["name"],
                record["token_prefix"],
                record["token_hash"],
                record["scopes_json"],
                record["created_at"],
                record["enabled"],
            ),
        )
        return public_token(record), token

    def set_enabled(self, user_id: str, token_id: str, enabled: bool) -> dict[str, Any]:
        record = get_database().one(
            "SELECT id, name, token_prefix, scopes_json, created_at, last_used_at, expires_at, enabled FROM mcp_tokens WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (token_id, user_id),
        )
        if not record:
            raise ApiError("MCP Token 不存在或已撤销", 404)
        get_database().execute("UPDATE mcp_tokens SET enabled = ? WHERE id = ?", (1 if enabled else 0, token_id))
        record["enabled"] = 1 if enabled else 0
        return public_token(record)

    def revoke_token(self, user_id: str, token_id: str) -> None:
        record = get_database().one(
            "SELECT id FROM mcp_tokens WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (token_id, user_id),
        )
        if not record:
            raise ApiError("MCP Token 不存在或已撤销", 404)
        get_database().execute("UPDATE mcp_tokens SET revoked_at = ? WHERE id = ?", (iso_now(), token_id))

    def authenticate(self, token: str) -> dict[str, Any] | None:
        record = get_database().one(
            """SELECT tokens.id, tokens.user_id, tokens.name, tokens.scopes_json, users.username,
                      users.email_verified, users.status
               FROM mcp_tokens AS tokens
               INNER JOIN users ON users.id = tokens.user_id
               WHERE tokens.token_hash = ?
                 AND tokens.revoked_at IS NULL
                 AND tokens.enabled = 1
                 AND users.email_verified = 1
                 AND users.status = 'active'
                 AND (tokens.expires_at IS NULL OR tokens.expires_at > ?)""",
            (token_hash(token), iso_now()),
        )
        if not record:
            return None
        get_database().execute("UPDATE mcp_tokens SET last_used_at = ? WHERE id = ?", (iso_now(), record["id"]))
        record["scopes"] = json.loads(record.pop("scopes_json"))
        return record
