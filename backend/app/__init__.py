from __future__ import annotations

from flask import Flask, abort, request, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .common.errors import ApiError
from .common.extensions import initialize_extensions
from .common.responses import error_response
from .config.settings import ROOT_DIR, settings
from .controllers.auth_controller import auth_bp
from .controllers.mcp_controller import mcp_bp
from .controllers.project_controller import projects_bp
from .controllers.system.health_controller import health_bp
from .services.project_import_service import resume_pending_import_jobs


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
    initialize_extensions()
    resume_pending_import_jobs()
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(mcp_bp)
    app.register_blueprint(projects_bp)

    @app.after_request
    def cors_headers(response):
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin in settings.frontend_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        return response

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return error_response(error.message, error.status)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_request(_error: RequestEntityTooLarge):
        return error_response("Sketch 文件超过 500 MB 限制", 413)

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return error_response(error.description, error.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("未处理的服务异常", exc_info=error)
        return error_response("服务内部错误，请查看后端日志", 500)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def frontend(path: str):
        if path.startswith("api/"):
            abort(404)
        frontend_dir = ROOT_DIR / "canvas-react" / "dist"
        if not frontend_dir.is_dir():
            return error_response("前端尚未构建，请先执行 npm run build", 503)
        requested = (frontend_dir / path).resolve()
        if path and requested.is_file() and frontend_dir.resolve() in requested.parents:
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, "index.html")

    return app
