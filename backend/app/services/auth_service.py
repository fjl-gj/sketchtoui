from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from flask import Request, Response

from ..common.errors import ApiError
from ..common.extensions import get_database, get_redis
from ..config.settings import settings


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
SESSION_COOKIE = "sketch_session"
VERIFY_TTL_SECONDS = 600
RESEND_COOLDOWN_SECONDS = 60
MAX_VERIFY_ATTEMPTS = 5


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return "$".join(("scrypt", "16384", "8", "1", base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode()))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_digest = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.urlsafe_b64decode(encoded_salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, base64.urlsafe_b64decode(encoded_digest))
    except (TypeError, ValueError):
        return False


def code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "username": user["username"],
        "phone": user.get("phone"),
        "emailVerified": bool(user.get("email_verified")),
        "emailVerifiedAt": user.get("email_verified_at"),
        "status": user.get("status", "active"),
        "lastLoginAt": user.get("last_login_at"),
        "createdAt": user["created_at"],
    }


def verification_key(email: str) -> str:
    return f"sketchtoui:email:verify:{email}"


def cooldown_key(email: str) -> str:
    return f"sketchtoui:email:cooldown:{email}"


def session_key(session_id: str) -> str:
    return f"sketchtoui:session:{session_id}"


def validate_email_and_username(payload: dict[str, Any]) -> tuple[str, str]:
    email = str(payload.get("email", "")).strip().lower()
    username = str(payload.get("username", "")).strip()
    if not EMAIL_PATTERN.fullmatch(email):
        raise ApiError("请输入有效的邮箱地址")
    if not USERNAME_PATTERN.fullmatch(username):
        raise ApiError("名称需为 3–64 位字母、数字、下划线或连字符")
    return email, username


def send_verification_email(email: str, username: str) -> None:
    redis = get_redis()
    if not redis.set(cooldown_key(email), "1", nx=True, ex=RESEND_COOLDOWN_SECONDS):
        raise ApiError("验证码已发送，请 60 秒后再试", 429)
    code = f"{secrets.randbelow(1_000_000):06d}"
    redis.set(verification_key(email), json.dumps({"hash": code_hash(code), "attempts": 0}), ex=VERIFY_TTL_SECONDS)
    content = f"你好，{username}：\n\n你的 Sketch Canvas 邮箱验证码是：{code}\n验证码 10 分钟内有效，请勿泄露给他人。\n"
    if settings.email_delivery == "console":
        print(f"\n[Email verification] To: {email}\n{content}")
        return
    if settings.email_delivery != "smtp" or not settings.smtp_host or not settings.smtp_sender:
        raise ApiError("SMTP 配置不完整，无法发送验证码", 500)
    message = EmailMessage()
    message["Subject"] = "Sketch Canvas 邮箱验证码"
    message["From"] = settings.smtp_sender
    message["To"] = email
    message.set_content(content)
    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    try:
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=20) as client:
            if settings.smtp_use_tls and not settings.smtp_use_ssl:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        redis.delete(verification_key(email), cooldown_key(email))
        raise ApiError("验证码发送失败，请检查 SMTP 服务与账号配置", 502) from error


def verify_registration_code(email: str, code: str) -> None:
    if not re.fullmatch(r"\d{6}", code.strip()):
        raise ApiError("请输入 6 位数字验证码")
    redis = get_redis()
    record_json = redis.get(verification_key(email))
    if not record_json:
        raise ApiError("验证码无效或已过期", 404)
    record = json.loads(record_json)
    if record["attempts"] >= MAX_VERIFY_ATTEMPTS:
        redis.delete(verification_key(email))
        raise ApiError("验证码错误次数过多，请重新获取", 429)
    if not hmac.compare_digest(record["hash"], code_hash(code.strip())):
        record["attempts"] += 1
        ttl = redis.ttl(verification_key(email))
        redis.set(verification_key(email), json.dumps(record), ex=max(1, ttl))
        raise ApiError("验证码不正确")
    redis.delete(verification_key(email))


def current_user(request: Request, require_verified: bool = False) -> dict[str, Any]:
    session_id = request.cookies.get(SESSION_COOKIE)
    user_id = get_redis().get(session_key(session_id)) if session_id else None
    if not user_id:
        raise ApiError("请先登录", 401)
    user = get_database().one(
        "SELECT id, email, username, phone, email_verified, email_verified_at, status, last_login_at, created_at, updated_at FROM users WHERE id = ?",
        (user_id,),
    )
    if not user:
        raise ApiError("登录已过期，请重新登录", 401)
    if user["status"] != "active":
        get_redis().delete(session_key(session_id))
        raise ApiError("该账户已被禁用", 403)
    if require_verified and not bool(user["email_verified"]):
        raise ApiError("请先完成邮箱验证", 403)
    return user


def issue_session(user_id: str) -> str:
    session_id = secrets.token_urlsafe(48)
    get_redis().set(session_key(session_id), user_id, ex=settings.session_days * 86400)
    return session_id


def apply_session_cookie(response: Response, session_id: str, max_age: int) -> Response:
    response.set_cookie(SESSION_COOKIE, session_id, max_age=max_age, httponly=True, samesite="Lax", secure=settings.app_base_url.startswith("https://"), path="/")
    return response


class AuthService:
    def send_registration_verification(self, payload: dict[str, Any]) -> None:
        email, username = validate_email_and_username(payload)
        if get_database().one("SELECT id FROM users WHERE email = ? OR username = ?", (email, username)):
            raise ApiError("邮箱或名称已被使用", 409)
        send_verification_email(email, username)

    def register(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        email, username = validate_email_and_username(payload)
        password = str(payload.get("password", ""))
        if len(password) < 8:
            raise ApiError("密码至少需要 8 位")
        database = get_database()
        if database.one("SELECT id FROM users WHERE email = ? OR username = ?", (email, username)):
            raise ApiError("邮箱或名称已被使用", 409)
        verify_registration_code(email, str(payload.get("code", "")))
        now = iso_now()
        user = {
            "id": uuid.uuid4().hex,
            "email": email,
            "username": username,
            "password_hash": hash_password(password),
            "email_verified": 1,
            "email_verified_at": now,
            "status": "active",
            "last_login_at": now,
            "created_at": now,
            "updated_at": now,
        }
        database.execute(
            """INSERT INTO users (
                   id, email, username, password_hash, email_verified, email_verified_at,
                   status, last_login_at, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user["id"], user["email"], user["username"], user["password_hash"],
                user["email_verified"], user["email_verified_at"], user["status"],
                user["last_login_at"], user["created_at"], user["updated_at"],
            ),
        )
        return user, issue_session(user["id"])

    def login(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        identity = str(payload.get("identity", "")).strip().lower()
        user = get_database().one(
            """SELECT id, email, username, phone, password_hash, email_verified, email_verified_at,
                      status, last_login_at, created_at, updated_at
               FROM users WHERE email = ? OR username = ?""",
            (identity, identity),
        )
        if not user or not verify_password(str(payload.get("password", "")), user["password_hash"]):
            raise ApiError("邮箱或名称、密码不正确", 401)
        if user["status"] != "active":
            raise ApiError("该账户已被禁用", 403)
        if not bool(user["email_verified"]):
            raise ApiError("请先完成邮箱验证", 403)
        now = iso_now()
        get_database().execute("UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?", (now, now, user["id"]))
        user["last_login_at"] = now
        user["updated_at"] = now
        return user, issue_session(user["id"])
