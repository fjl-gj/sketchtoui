from urllib.parse import unquote
from io import BytesIO

from flask import Blueprint, request, send_file

from ..common.errors import ApiError
from ..services.auth_service import current_user
from ..services.project_import_service import ProjectImportService


projects_bp = Blueprint("projects", __name__)
service = ProjectImportService()


@projects_bp.get("/api/projects")
def projects():
    user = current_user(request, require_verified=True)
    return {"projects": service.list_projects(user["id"])}


@projects_bp.post("/api/projects")
def import_project():
    user = current_user(request, require_verified=True)
    filename = unquote(request.headers.get("X-Filename", ""))
    name = unquote(request.headers.get("X-Project-Name", ""))
    content_length = request.content_length or 0
    return {"import": service.queue_import(user["id"], filename, name, request.stream, content_length)}, 202


@projects_bp.post("/api/projects/<project_id>/versions")
def reimport_project(project_id: str):
    user = current_user(request, require_verified=True)
    filename = unquote(request.headers.get("X-Filename", ""))
    content_length = request.content_length or 0
    return {"import": service.queue_reimport(user["id"], project_id, filename, request.stream, content_length)}, 202


@projects_bp.get("/api/projects/<project_id>/versions")
def project_versions(project_id: str):
    user = current_user(request, require_verified=True)
    return {"versions": service.list_versions(user["id"], project_id)}


@projects_bp.delete("/api/projects/<project_id>")
def delete_project(project_id: str):
    user = current_user(request, require_verified=True)
    service.delete_project(user["id"], project_id)
    return {"ok": True}


@projects_bp.get("/api/imports/<job_id>")
def import_status(job_id: str):
    user = current_user(request, require_verified=True)
    return {"import": service.get_job(user["id"], job_id)}


@projects_bp.get("/api/projects/<project_id>/manifest")
def manifest(project_id: str):
    payload, content_type = service.read_object(current_user(request, require_verified=True)["id"], project_id, "canvas/manifest.json")
    return send_file(BytesIO(payload), mimetype=content_type, conditional=True, max_age=0)


@projects_bp.get("/api/projects/<project_id>/canvas/<path:relative_path>")
def canvas_file(project_id: str, relative_path: str):
    payload, content_type = service.read_object(current_user(request, require_verified=True)["id"], project_id, f"canvas/{relative_path}")
    return send_file(BytesIO(payload), mimetype=content_type, conditional=True, max_age=0)


@projects_bp.get("/api/projects/<project_id>/assets/<path:relative_path>")
def asset_file(project_id: str, relative_path: str):
    payload, content_type = service.read_object(current_user(request, require_verified=True)["id"], project_id, f"sketch/{relative_path}")
    return send_file(BytesIO(payload), mimetype=content_type, conditional=True, max_age=0)
