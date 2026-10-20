from flask import Blueprint, request

from ..config.settings import settings
from ..services.auth_service import current_user
from ..services.mcp_token_service import McpTokenService


mcp_bp = Blueprint("mcp", __name__, url_prefix="/api/mcp")
service = McpTokenService()


@mcp_bp.get("/config")
def config():
    current_user(request, require_verified=True)
    return {"url": settings.mcp_public_url}


@mcp_bp.get("/tokens")
def tokens():
    user = current_user(request, require_verified=True)
    return {"tokens": service.list_tokens(user["id"])}


@mcp_bp.post("/tokens")
def create_token():
    user = current_user(request, require_verified=True)
    payload = request.get_json(silent=True) or {}
    token, value = service.create_token(user["id"], str(payload.get("name", "")))
    return {"token": token, "value": value}, 201


@mcp_bp.delete("/tokens/<token_id>")
def revoke_token(token_id: str):
    user = current_user(request, require_verified=True)
    service.revoke_token(user["id"], token_id)
    return {"ok": True}


@mcp_bp.patch("/tokens/<token_id>")
def set_token_enabled(token_id: str):
    user = current_user(request, require_verified=True)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("enabled"), bool):
        return {"error": "enabled 必须为布尔值"}, 400
    return {"token": service.set_enabled(user["id"], token_id, payload["enabled"])}
