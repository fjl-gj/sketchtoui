from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO

from ..common.errors import ApiError
from ..common.extensions import get_cache, get_database, get_storage
from ..config.settings import ROOT_DIR, settings
from .auth_service import iso_now
from sketch_to_canvas_site import generate_canvas_site


TEMP_DIR = ROOT_DIR / "data" / "tmp"
PROJECT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
MAX_UPLOAD_BYTES = settings.import_max_upload_bytes
JOB_TTL_SECONDS = 24 * 3600
ARCHIVE_CHUNK_BYTES = 1024 * 1024
IMPORT_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, settings.import_max_workers), thread_name_prefix="sketch-import")
IMPORT_TASK_OWNER = f"api-{os.getpid()}"
logger = logging.getLogger(__name__)


def project_json(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": project["id"],
        "name": project["name"],
        "sourceFilename": project["filename"],
        "createdAt": project["created_at"],
        "updatedAt": project.get("updated_at"),
        "groupCount": project["group_count"],
        "status": project.get("status", "ready"),
        "currentVersionId": project.get("current_version_id"),
        "currentVersionNumber": project.get("current_version_number"),
    }


def import_job_json(job: dict[str, Any]) -> dict[str, Any]:
    return {"id": job["id"], "stage": job["stage"], "progress": job["progress"], "message": job["message"], "project": job.get("project"), "error": job.get("error")}


def project_version_json(version: dict[str, Any], current_version_id: str | None) -> dict[str, Any]:
    return {
        "id": version["id"],
        "versionNumber": version["version_number"],
        "filename": version["filename"],
        "status": version["status"],
        "sourceBytes": version["source_bytes"],
        "totalBytes": version["total_bytes"],
        "groupCount": version["group_count"],
        "artboardCount": version["artboard_count"],
        "layerCount": version["layer_count"],
        "createdAt": version["created_at"],
        "completedAt": version["completed_at"],
        "error": version["error_message"],
        "isCurrent": version["id"] == current_version_id,
    }


def object_prefix(user_id: str, project_id: str) -> str:
    return f"users/{user_id}/projects/{project_id}"


def version_object_prefix(user_id: str, project_id: str, version_id: str) -> str:
    return f"{object_prefix(user_id, project_id)}/versions/{version_id}"


def job_key(job_id: str) -> str:
    return f"sketchtoui:import:{job_id}"


def temp_dir_for_job(job_id: str) -> Path:
    return TEMP_DIR / job_id


def submit_import_job(job_id: str) -> None:
    IMPORT_EXECUTOR.submit(run_import_job, job_id)


def safe_relative_path(value: str) -> str:
    posix_path = PurePosixPath(value.replace("\\", "/"))
    windows_path = PureWindowsPath(value)
    parts = posix_path.parts
    if (
        not value
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in parts
    ):
        raise ApiError("无效的文件路径")
    return "/".join(parts)


def extract_sketch_archive(source_path: Path, target_dir: Path) -> None:
    try:
        with zipfile.ZipFile(source_path) as archive:
            members = archive.infolist()
            if len(members) > settings.import_max_archive_entries:
                raise ApiError(f"Sketch 压缩包文件数量超过 {settings.import_max_archive_entries} 个限制")

            expected_total = 0
            for member in members:
                relative_path = PurePosixPath(member.filename.replace("\\", "/"))
                if relative_path.is_absolute() or not relative_path.parts or relative_path.parts[0].endswith(":") or ".." in relative_path.parts:
                    raise ApiError("Sketch 文件包含不安全的压缩路径")
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ApiError("Sketch 文件不能包含符号链接")
                if member.flag_bits & 0x1:
                    raise ApiError("Sketch 文件不能包含加密压缩条目")
                if member.is_dir():
                    continue
                if member.file_size > settings.import_max_archive_file_bytes:
                    raise ApiError("Sketch 压缩包包含超过单文件大小限制的内容")
                expected_total += member.file_size
                if expected_total > settings.import_max_extracted_bytes:
                    raise ApiError("Sketch 解压后的总大小超过限制")
                if member.file_size and (not member.compress_size or member.file_size / member.compress_size > settings.import_max_compression_ratio):
                    raise ApiError("Sketch 压缩包压缩比异常，已拒绝解压")

            extracted_total = 0
            target_dir.mkdir(parents=True, exist_ok=True)
            for member in members:
                relative_path = PurePosixPath(member.filename.replace("\\", "/"))
                destination = target_dir.joinpath(*relative_path.parts)
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as output:
                    while chunk := source.read(ARCHIVE_CHUNK_BYTES):
                        extracted_total += len(chunk)
                        if extracted_total > settings.import_max_extracted_bytes:
                            raise ApiError("Sketch 解压后的总大小超过限制")
                        output.write(chunk)
    except zipfile.BadZipFile as error:
        raise ApiError("上传文件不是有效的 Sketch 压缩包") from error


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def get_job(job_id: str) -> dict[str, Any]:
    raw = get_cache().get(job_key(job_id))
    if raw:
        return json.loads(raw)
    record = get_database().one(
        """SELECT id, user_id, project_id, status, stage, progress, message, error_message
           FROM import_jobs WHERE id = ?""",
        (job_id,),
    )
    if not record:
        raise ApiError("导入任务不存在或已过期", 404)
    job = {
        "id": record["id"],
        "userId": record["user_id"],
        "stage": record["stage"],
        "progress": record["progress"],
        "message": record["message"],
    }
    if record["status"] == "succeeded":
        project = get_database().one(
            """SELECT projects.id, projects.name, projects.filename, projects.group_count, projects.created_at,
                      projects.updated_at, projects.status, projects.current_version_id,
                      project_versions.version_number AS current_version_number
               FROM projects
               LEFT JOIN project_versions ON project_versions.id = projects.current_version_id
               WHERE projects.id = ? AND projects.user_id = ?""",
            (record["project_id"], record["user_id"]),
        )
        if project:
            job["project"] = project_json(project)
    if record["error_message"]:
        job["error"] = record["error_message"]
    return job


def update_job(job_id: str, **updates: Any) -> None:
    job = get_job(job_id)
    job.update(updates)
    get_cache().set(job_key(job_id), json.dumps(job, ensure_ascii=False), ex=JOB_TTL_SECONDS)
    stage = str(job["stage"])
    status = {"queued": "queued", "complete": "succeeded", "failed": "failed"}.get(stage, "running")
    now = iso_now()
    get_database().execute(
        """UPDATE import_jobs
           SET status = ?, stage = ?, progress = ?, message = ?, error_message = ?,
               started_at = CASE WHEN ? = 'running' AND started_at IS NULL THEN ? ELSE started_at END,
               finished_at = CASE WHEN ? IN ('succeeded', 'failed') THEN ? ELSE finished_at END
           WHERE id = ?""",
        (
            status,
            stage,
            int(job["progress"]),
            str(job["message"]),
            job.get("error"),
            status,
            now,
            status,
            now,
            job_id,
        ),
    )


def upload_tree(local_dir: Path, prefix: str) -> None:
    client = get_storage()
    for file_path in local_dir.rglob("*"):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(local_dir).as_posix()
        client.put_file(f"{prefix}/{relative_path}", file_path)


def remove_object_tree(prefix: str) -> None:
    get_storage().delete_prefix(prefix)


def process_import(job_id: str, user_id: str, project: dict[str, Any], version: dict[str, Any], temp_dir: Path) -> bool:
    try:
        update_job(job_id, stage="extracting", progress=20, message="正在安全解压 Sketch 文件")
        get_database().execute("UPDATE project_versions SET status = 'processing' WHERE id = ?", (version["id"],))
        extract_sketch_archive(temp_dir / "source.sketch", temp_dir / "sketch")
        update_job(job_id, stage="parsing", progress=45, message="正在解析页面、画板与图层")

        def report(completed: int, total: int, group_name: str) -> None:
            update_job(job_id, stage="parsing", progress=45 + round(completed / max(1, total) * 45), message=f"正在解析分组：{group_name}")

        groups = generate_canvas_site(temp_dir / "sketch", temp_dir / "canvas", progress_callback=report)
        update_job(job_id, stage="uploading", progress=92, message="正在保存项目文件")
        upload_tree(temp_dir, version["object_prefix"])
        project["group_count"] = len(groups)
        artboard_count = sum(group["artboardCount"] for group in groups)
        layer_count = sum(group["layerCount"] for group in groups)
        extracted_bytes = directory_bytes(temp_dir / "sketch")
        canvas_bytes = directory_bytes(temp_dir / "canvas")
        source_bytes = (temp_dir / "source.sketch").stat().st_size
        total_bytes = source_bytes + extracted_bytes + canvas_bytes
        completed_at = iso_now()
        get_database().execute(
            """UPDATE project_versions
               SET status = 'ready', manifest_path = ?, group_count = ?, artboard_count = ?, layer_count = ?,
                   source_bytes = ?, extracted_bytes = ?, canvas_bytes = ?, preview_bytes = 0, total_bytes = ?,
                   completed_at = ?, error_code = NULL, error_message = NULL
               WHERE id = ?""",
            (
                "canvas/manifest.json",
                project["group_count"],
                artboard_count,
                layer_count,
                source_bytes,
                extracted_bytes,
                canvas_bytes,
                total_bytes,
                completed_at,
                version["id"],
            ),
        )
        project.update({
            "filename": version["filename"],
            "status": "ready",
            "current_version_id": version["id"],
            "current_version_number": version["version_number"],
            "updated_at": completed_at,
        })
        get_database().execute(
            """UPDATE projects
               SET filename = ?, group_count = ?, current_version_id = ?, status = 'ready', updated_at = ?
               WHERE id = ? AND user_id = ?""",
            (version["filename"], project["group_count"], version["id"], completed_at, project["id"], user_id),
        )
        update_job(job_id, stage="complete", progress=100, message="画布已生成并保存到 MinIO", project=project_json(project))
        return True
    except Exception as error:
        failed_at = iso_now()
        try:
            remove_object_tree(version["object_prefix"])
        except Exception:
            pass
        get_database().execute(
            "UPDATE project_versions SET status = 'failed', error_code = 'import_failed', error_message = ?, completed_at = ? WHERE id = ?",
            (str(error), failed_at, version["id"]),
        )
        if not project.get("current_version_id"):
            get_database().execute(
                "UPDATE projects SET status = 'failed', updated_at = ? WHERE id = ? AND user_id = ?",
                (failed_at, project["id"], user_id),
            )
        update_job(job_id, stage="failed", progress=100, message="导入失败", error=str(error))
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def claim_import_job(job_id: str, task_owner: str) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    database = get_database()
    record = database.one(
        """SELECT import_jobs.user_id, import_jobs.project_id, import_jobs.project_version_id,
                  projects.id AS project_id_value, projects.name, projects.filename, projects.group_count,
                  projects.created_at, projects.updated_at, projects.status AS project_status,
                  projects.current_version_id,
                  project_versions.id AS version_id, project_versions.version_number, project_versions.filename AS version_filename,
                  project_versions.source_sha256, project_versions.object_prefix, project_versions.created_at AS version_created_at
           FROM import_jobs
           JOIN projects ON projects.id = import_jobs.project_id AND projects.user_id = import_jobs.user_id
           JOIN project_versions ON project_versions.id = import_jobs.project_version_id AND project_versions.project_id = projects.id
           WHERE import_jobs.id = ? AND import_jobs.status = 'queued'""",
        (job_id,),
    )
    if not record:
        return None
    claimed = database.execute(
        """UPDATE import_jobs
           SET status = 'running', worker_id = ?, attempt = attempt + 1,
               started_at = COALESCE(started_at, ?)
           WHERE id = ? AND status = 'queued'""",
        (task_owner, iso_now(), job_id),
    )
    if claimed != 1:
        return None
    project = {
        "id": record["project_id_value"],
        "name": record["name"],
        "filename": record["filename"],
        "group_count": record["group_count"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "status": record["project_status"],
        "current_version_id": record["current_version_id"],
    }
    version = {
        "id": record["version_id"],
        "project_id": record["project_id"],
        "version_number": record["version_number"],
        "filename": record["version_filename"],
        "source_sha256": record["source_sha256"],
        "object_prefix": record["object_prefix"],
        "created_at": record["version_created_at"],
    }
    return record["user_id"], project, version


def run_import_job(job_id: str) -> None:
    claimed = claim_import_job(job_id, IMPORT_TASK_OWNER)
    if not claimed:
        return
    user_id, project, version = claimed
    succeeded = process_import(job_id, user_id, project, version, temp_dir_for_job(job_id))
    logger.info("Import task %s finished with status=%s", job_id, "succeeded" if succeeded else "failed")


def resume_pending_import_jobs() -> int:
    database = get_database()
    interrupted_jobs = database.all("SELECT id, user_id FROM import_jobs WHERE status = 'running'")
    database.execute(
        """UPDATE import_jobs
           SET status = 'queued', stage = 'queued', progress = 5,
               message = '服务已恢复，等待重新处理', worker_id = NULL
           WHERE status = 'running'"""
    )
    for job in interrupted_jobs:
        get_cache().set(
            job_key(job["id"]),
            json.dumps({"id": job["id"], "userId": job["user_id"], "stage": "queued", "progress": 5, "message": "服务已恢复，等待重新处理"}, ensure_ascii=False),
            ex=JOB_TTL_SECONDS,
    )
    for record in database.all("SELECT id FROM import_jobs WHERE status = 'queued'"):
        submit_import_job(record["id"])
    return len(interrupted_jobs)


class ProjectImportService:
    def list_projects(self, user_id: str) -> list[dict[str, Any]]:
        return [
            project_json(project)
            for project in get_database().all(
                """SELECT projects.id, projects.name, projects.filename, projects.group_count, projects.created_at,
                          projects.updated_at, projects.status, projects.current_version_id,
                          project_versions.version_number AS current_version_number
                   FROM projects
                   LEFT JOIN project_versions ON project_versions.id = projects.current_version_id
                   WHERE projects.user_id = ? AND projects.status = 'ready'
                   ORDER BY projects.updated_at DESC, projects.created_at DESC""",
                (user_id,),
            )
        ]

    def queue_import(self, user_id: str, filename: str, name: str, stream: BinaryIO, content_length: int) -> dict[str, Any]:
        if content_length <= 0:
            raise ApiError("请选择要导入的 .sketch 文件")
        if content_length > MAX_UPLOAD_BYTES:
            raise ApiError("Sketch 文件超过 500 MB 限制")
        if not filename.lower().endswith(".sketch"):
            raise ApiError("只支持导入 .sketch 文件")
        project_id = uuid.uuid4().hex
        job_id = uuid.uuid4().hex
        version_id = uuid.uuid4().hex
        temp_dir = temp_dir_for_job(job_id)
        try:
            temp_dir.mkdir(parents=True, exist_ok=False)
            remaining = content_length
            with (temp_dir / "source.sketch").open("wb") as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ApiError("上传内容不完整")
                    output.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        now = iso_now()
        project = {
            "id": project_id,
            "name": name.strip() or Path(filename).stem,
            "filename": filename,
            "group_count": 0,
            "status": "importing",
            "current_version_id": None,
            "created_at": now,
            "updated_at": now,
        }
        version = {
            "id": version_id,
            "project_id": project_id,
            "version_number": 1,
            "filename": filename,
            "source_sha256": file_sha256(temp_dir / "source.sketch"),
            "object_prefix": version_object_prefix(user_id, project_id, version_id),
            "created_at": now,
        }
        database = get_database()
        try:
            database.execute(
                """INSERT INTO projects (id, user_id, name, filename, group_count, current_version_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project["id"], user_id, project["name"], project["filename"], project["group_count"],
                    project["current_version_id"], project["status"], project["created_at"], project["updated_at"],
                ),
            )
            database.execute(
                """INSERT INTO project_versions (
                       id, project_id, version_number, filename, source_sha256, object_prefix, status, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version["id"], version["project_id"], version["version_number"], version["filename"],
                    version["source_sha256"], version["object_prefix"], "pending", version["created_at"],
                ),
            )
            database.execute(
                """INSERT INTO import_jobs (
                       id, user_id, project_id, project_version_id, status, stage, progress, message, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, user_id, project_id, version_id, "queued", "queued", 5, "文件已接收，等待开始解析", now),
            )
        except Exception:
            database.execute("DELETE FROM import_jobs WHERE project_id = ?", (project_id,))
            database.execute("DELETE FROM project_versions WHERE project_id = ?", (project_id,))
            database.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        job = {"id": job_id, "userId": user_id, "stage": "queued", "progress": 5, "message": "文件已接收，等待开始解析"}
        try:
            get_cache().set(job_key(job_id), json.dumps(job, ensure_ascii=False), ex=JOB_TTL_SECONDS)
            submit_import_job(job_id)
        except Exception:
            get_cache().delete(job_key(job_id))
            database.execute("DELETE FROM import_jobs WHERE id = ?", (job_id,))
            database.execute("DELETE FROM project_versions WHERE id = ?", (version_id,))
            database.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return import_job_json(job)

    def queue_reimport(self, user_id: str, project_id: str, filename: str, stream: BinaryIO, content_length: int) -> dict[str, Any]:
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ApiError("无效的项目 ID")
        if content_length <= 0:
            raise ApiError("请选择要导入的 .sketch 文件")
        if content_length > MAX_UPLOAD_BYTES:
            raise ApiError("Sketch 文件超过 500 MB 限制")
        if not filename.lower().endswith(".sketch"):
            raise ApiError("只支持导入 .sketch 文件")

        database = get_database()
        project = database.one(
            """SELECT id, name, filename, group_count, created_at, updated_at, status, current_version_id
               FROM projects WHERE id = ? AND user_id = ?""",
            (project_id, user_id),
        )
        if not project:
            raise ApiError("项目不存在或无权访问", 404)
        if database.one("SELECT id FROM project_versions WHERE project_id = ? AND status IN ('pending', 'processing')", (project_id,)):
            raise ApiError("该项目已有导入任务正在执行，请等待完成后再试", 409)

        job_id = uuid.uuid4().hex
        version_id = uuid.uuid4().hex
        temp_dir = temp_dir_for_job(job_id)
        try:
            temp_dir.mkdir(parents=True, exist_ok=False)
            remaining = content_length
            with (temp_dir / "source.sketch").open("wb") as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ApiError("上传内容不完整")
                    output.write(chunk)
                    remaining -= len(chunk)

            now = iso_now()
            latest_version = database.one(
                "SELECT COALESCE(MAX(version_number), 0) AS latest_version FROM project_versions WHERE project_id = ?",
                (project_id,),
            )
            version = {
                "id": version_id,
                "project_id": project_id,
                "version_number": int(latest_version["latest_version"]) + 1,
                "filename": filename,
                "source_sha256": file_sha256(temp_dir / "source.sketch"),
                "object_prefix": version_object_prefix(user_id, project_id, version_id),
                "created_at": now,
            }
            database.execute(
                """INSERT INTO project_versions (
                       id, project_id, version_number, filename, source_sha256, object_prefix, status, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version["id"], version["project_id"], version["version_number"], version["filename"],
                    version["source_sha256"], version["object_prefix"], "pending", version["created_at"],
                ),
            )
            database.execute(
                """INSERT INTO import_jobs (
                       id, user_id, project_id, project_version_id, status, stage, progress, message, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, user_id, project_id, version_id, "queued", "queued", 5, "新版本文件已接收，等待开始解析", now),
            )
        except Exception:
            database.execute("DELETE FROM import_jobs WHERE id = ?", (job_id,))
            database.execute("DELETE FROM project_versions WHERE id = ?", (version_id,))
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        job = {"id": job_id, "userId": user_id, "stage": "queued", "progress": 5, "message": "新版本文件已接收，等待开始解析"}
        try:
            get_cache().set(job_key(job_id), json.dumps(job, ensure_ascii=False), ex=JOB_TTL_SECONDS)
            submit_import_job(job_id)
        except Exception:
            get_cache().delete(job_key(job_id))
            database.execute("DELETE FROM import_jobs WHERE id = ?", (job_id,))
            database.execute("DELETE FROM project_versions WHERE id = ?", (version_id,))
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return import_job_json(job)

    def list_versions(self, user_id: str, project_id: str) -> list[dict[str, Any]]:
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ApiError("无效的项目 ID")
        project = get_database().one(
            "SELECT current_version_id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user_id),
        )
        if not project:
            raise ApiError("项目不存在或无权访问", 404)
        versions = get_database().all(
            """SELECT id, version_number, filename, source_bytes, total_bytes, group_count, artboard_count,
                      layer_count, status, created_at, completed_at, error_message
               FROM project_versions WHERE project_id = ? ORDER BY version_number DESC""",
            (project_id,),
        )
        return [project_version_json(version, project["current_version_id"]) for version in versions]

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        job = get_job(job_id)
        if job["userId"] != user_id:
            raise ApiError("导入任务不存在或无权访问", 404)
        return import_job_json(job)

    def delete_project(self, user_id: str, project_id: str) -> None:
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ApiError("无效的项目 ID")
        project = get_database().one("SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
        if not project:
            raise ApiError("项目不存在或无权访问", 404)
        remove_object_tree(object_prefix(user_id, project_id))
        get_database().execute("DELETE FROM import_jobs WHERE project_id = ?", (project_id,))
        get_database().execute("DELETE FROM project_versions WHERE project_id = ?", (project_id,))
        get_database().execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))

    def object_name(self, user_id: str, project_id: str, relative_path: str) -> str:
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ApiError("无效的项目 ID")
        project = get_database().one(
            "SELECT id, current_version_id, status FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user_id),
        )
        if not project:
            raise ApiError("项目不存在或无权访问", 404)
        if project["status"] != "ready":
            raise ApiError("项目仍在导入或导入失败，暂时无法读取", 409)
        if not project["current_version_id"]:
            return f"{object_prefix(user_id, project_id)}/{safe_relative_path(relative_path)}"
        version = get_database().one(
            "SELECT object_prefix FROM project_versions WHERE id = ? AND project_id = ? AND status = 'ready'",
            (project["current_version_id"], project_id),
        )
        if not version:
            raise ApiError("当前项目版本不可用", 409)
        return f"{version['object_prefix']}/{safe_relative_path(relative_path)}"

    def read_object(self, user_id: str, project_id: str, relative_path: str) -> tuple[bytes, str]:
        object_name = self.object_name(user_id, project_id, relative_path)
        try:
            return get_storage().read_object(object_name)
        except FileNotFoundError as error:
            raise ApiError("请求的项目文件不存在", 404) from error
