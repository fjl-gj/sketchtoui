from flask import Blueprint, jsonify, request

from ..common.errors import ApiError
from ..config.settings import settings
from ..services.auth_service import SESSION_COOKIE, AuthService, apply_session_cookie, current_user, public_user, session_key


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
service = AuthService()


def body() -> dict:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ApiError("请求必须是 JSON 对象")
    return value


@auth_bp.get("/me")
def me():
    return {"user": public_user(current_user(request))}


@auth_bp.post("/send-verification")
def send_verification():
    service.send_registration_verification(body())
    return {"message": "6 位验证码已发送，请查收邮箱"}


@auth_bp.post("/register")
def register():
    user, session_id = service.register(body())
    response = jsonify({"user": public_user(user), "message": "注册成功，请查收 6 位邮箱验证码"})
    response.status_code = 201
    return apply_session_cookie(response, session_id, settings.session_days * 86400)


@auth_bp.post("/login")
def login():
    user, session_id = service.login(body())
    return apply_session_cookie(jsonify({"user": public_user(user)}), session_id, settings.session_days * 86400)


@auth_bp.post("/logout")
def logout():
    try:
        session_id = request.cookies.get(SESSION_COOKIE)
        if session_id:
            from ..common.extensions import get_redis
            get_redis().delete(session_key(session_id))
    except ApiError:
        pass
    return apply_session_cookie(jsonify({"ok": True}), "", 0)
