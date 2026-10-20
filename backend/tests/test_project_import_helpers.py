from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.common.errors import ApiError
from app.services import project_import_service as imports
from app.services.project_import_service import ProjectImportService, directory_bytes, extract_sketch_archive, file_sha256, get_job, safe_relative_path


class ImportRedis:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.values: dict[str, str] = {}

    def get(self, _key: str) -> str | None:
        return self.value

    def set(self, key: str, value: str, **_kwargs) -> bool:
        self.values[key] = value
        return True


class ImportHelperTests(unittest.TestCase):
    def test_paths_hashes_and_secure_archive_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "source.sketch"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("document.json", "{}")
                archive.writestr("images/icon.png", b"icon")
            limits = SimpleNamespace(import_max_archive_entries=10, import_max_archive_file_bytes=1000, import_max_extracted_bytes=2000, import_max_compression_ratio=100)
            with patch.object(imports, "settings", limits):
                extract_sketch_archive(archive_path, root / "out")
            self.assertTrue((root / "out" / "images" / "icon.png").is_file())
            self.assertEqual(directory_bytes(root / "out"), len(b"{}") + len(b"icon"))
            self.assertEqual(len(file_sha256(root / "out" / "document.json")), 64)
            self.assertEqual(safe_relative_path("canvas/desktop/canvas.json"), "canvas/desktop/canvas.json")
            for unsafe in ("", "../secret", "/absolute", "folder/../../secret"):
                with self.assertRaises(ApiError):
                    safe_relative_path(unsafe)
            bad_archive = root / "bad.sketch"
            with zipfile.ZipFile(bad_archive, "w") as archive:
                archive.writestr("../escape.txt", "bad")
            with patch.object(imports, "settings", limits), self.assertRaises(ApiError):
                extract_sketch_archive(bad_archive, root / "bad-out")
            with (root / "not-a-zip.sketch").open("wb") as output:
                output.write(b"not zip")
            with patch.object(imports, "settings", limits), self.assertRaises(ApiError):
                extract_sketch_archive(root / "not-a-zip.sketch", root / "bad-out")

    def test_job_lookup_prefers_redis_then_rehydrates_database(self) -> None:
        redis = ImportRedis(json.dumps({"id": "job", "userId": "user", "stage": "running", "progress": 30, "message": "working"}))
        with patch.object(imports, "get_redis", return_value=redis):
            self.assertEqual(get_job("job")["progress"], 30)
        redis = ImportRedis()
        database = Mock()
        database.one.side_effect = [
            {"id": "job", "user_id": "user", "project_id": "project", "status": "succeeded", "stage": "complete", "progress": 100, "message": "done", "error_message": None},
            {"id": "project", "name": "Project", "filename": "source.sketch", "group_count": 1, "created_at": "created", "updated_at": "updated", "status": "ready", "current_version_id": "version", "current_version_number": 1},
        ]
        with patch.object(imports, "get_redis", return_value=redis), patch.object(imports, "get_database", return_value=database):
            result = get_job("job")
        self.assertEqual(result["project"]["id"], "project")
        self.assertEqual(result["stage"], "complete")

    def test_project_object_resolution_reading_and_validation(self) -> None:
        service = ProjectImportService()
        database = Mock()
        database.one.side_effect = [
            {"id": "project", "current_version_id": "version", "status": "ready"},
            {"object_prefix": "users/user/projects/project/versions/version"},
            {"id": "project", "current_version_id": "version", "status": "ready"},
            {"object_prefix": "users/user/projects/project/versions/version"},
        ]
        response = SimpleNamespace(read=lambda: b"payload", headers={"Content-Type": "image/png"}, close=Mock(), release_conn=Mock())
        minio = SimpleNamespace(get_object=lambda *_args: response)
        with patch.object(imports, "get_database", return_value=database), patch.object(imports, "get_minio", return_value=minio), patch.object(imports, "settings", SimpleNamespace(minio_bucket="bucket")):
            name = service.object_name("user", "a" * 32, "canvas/manifest.json")
            payload, content_type = service.read_object("user", "a" * 32, "images/icon.png")
        self.assertTrue(name.endswith("canvas/manifest.json"))
        self.assertEqual(payload, b"payload")
        self.assertEqual(content_type, "image/png")
        response.close.assert_called_once()
        response.release_conn.assert_called_once()
        with self.assertRaises(ApiError):
            service.object_name("user", "invalid", "canvas/manifest.json")
        with self.assertRaises(ApiError):
            service.queue_import("user", "source.txt", "", io.BytesIO(b"x"), 1)
        with self.assertRaises(ApiError):
            service.queue_import("user", "source.sketch", "", io.BytesIO(b""), 0)

    def test_import_job_lifecycle_processing_and_recovery(self) -> None:
        database = Mock()
        redis = ImportRedis(json.dumps({"id": "job", "userId": "user", "stage": "queued", "progress": 5, "message": "waiting"}))
        with patch.object(imports, "get_database", return_value=database), patch.object(imports, "get_redis", return_value=redis), patch.object(imports, "iso_now", return_value="now"):
            imports.update_job("job", stage="complete", progress=100, message="done", project={"id": "project"})
        self.assertEqual(json.loads(redis.values[imports.job_key("job")])["stage"], "complete")

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            (temporary / "source.sketch").write_bytes(b"source")
            updates = Mock()
            database.execute.reset_mock()
            def generate(_sketch: Path, canvas: Path, progress_callback):
                canvas.mkdir(parents=True)
                (canvas / "manifest.json").write_text("{}", encoding="utf-8")
                progress_callback(1, 1, "登录")
                return [{"artboardCount": 2, "layerCount": 8}]

            project = {"id": "project", "name": "Project", "filename": "source.sketch", "group_count": 0, "created_at": "created", "updated_at": "created", "current_version_id": None}
            version = {"id": "version", "version_number": 1, "filename": "source.sketch", "object_prefix": "prefix"}
            with patch.object(imports, "get_database", return_value=database), patch.object(imports, "update_job", updates), patch.object(imports, "extract_sketch_archive", side_effect=lambda _source, target: target.mkdir()), patch.object(imports, "generate_canvas_site", side_effect=generate), patch.object(imports, "upload_tree"), patch.object(imports, "directory_bytes", side_effect=[10, 20]), patch.object(imports, "iso_now", return_value="done"):
                self.assertTrue(imports.process_import("job", "user", project, version, temporary))
            self.assertEqual(updates.call_args_list[-1].kwargs["stage"], "complete")
            self.assertFalse(temporary.exists())

        failing_database = Mock()
        failed_updates = Mock()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            temporary.mkdir(exist_ok=True)
            with patch.object(imports, "get_database", return_value=failing_database), patch.object(imports, "update_job", failed_updates), patch.object(imports, "extract_sketch_archive", side_effect=ValueError("broken")), patch.object(imports, "remove_object_tree", side_effect=RuntimeError("storage")), patch.object(imports, "iso_now", return_value="failed"):
                self.assertFalse(imports.process_import("job", "user", {"id": "project", "current_version_id": None}, {"id": "version", "object_prefix": "prefix"}, temporary))
        self.assertEqual(failed_updates.call_args.kwargs["stage"], "failed")

        record = {
            "user_id": "user", "project_id": "project", "project_version_id": "version", "project_id_value": "project", "name": "Project", "filename": "source.sketch", "group_count": 1,
            "created_at": "created", "updated_at": "updated", "project_status": "importing", "current_version_id": None,
            "version_id": "version", "version_number": 1, "version_filename": "source.sketch", "source_sha256": "hash", "object_prefix": "prefix", "version_created_at": "created",
        }
        database.one.return_value = record
        database.execute.return_value = 1
        with patch.object(imports, "get_database", return_value=database), patch.object(imports, "iso_now", return_value="now"):
            claimed = imports.claim_import_job("job", "worker")
        self.assertEqual(claimed[0], "user")
        database.execute.return_value = 0
        with patch.object(imports, "get_database", return_value=database), patch.object(imports, "iso_now", return_value="now"):
            self.assertIsNone(imports.claim_import_job("job", "worker"))
        database.one.return_value = None
        with patch.object(imports, "get_database", return_value=database):
            self.assertIsNone(imports.claim_import_job("job", "worker"))

        resume_database = Mock()
        resume_database.all.side_effect = [[{"id": "running", "user_id": "user"}], [{"id": "running"}, {"id": "queued"}]]
        submitted = Mock()
        with patch.object(imports, "get_database", return_value=resume_database), patch.object(imports, "get_redis", return_value=ImportRedis()), patch.object(imports, "submit_import_job", submitted):
            self.assertEqual(imports.resume_pending_import_jobs(), 1)
        self.assertEqual(submitted.call_count, 2)

    def test_upload_project_and_version_operations(self) -> None:
        client = Mock()
        client.list_objects.return_value = [SimpleNamespace(object_name="prefix/one"), SimpleNamespace(object_name="prefix/two")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.txt").write_text("one", encoding="utf-8")
            (root / "folder").mkdir()
            (root / "folder" / "two.png").write_bytes(b"two")
            with patch.object(imports, "get_minio", return_value=client), patch.object(imports, "settings", SimpleNamespace(minio_bucket="bucket")):
                imports.upload_tree(root, "prefix")
                imports.remove_object_tree("prefix")
        self.assertEqual(client.fput_object.call_count, 2)
        self.assertEqual(client.remove_object.call_count, 2)

        project_id = "a" * 32
        database = Mock()
        database.all.return_value = [{"id": project_id, "name": "Project", "filename": "source.sketch", "group_count": 1, "created_at": "created", "updated_at": "updated", "status": "ready", "current_version_id": "version", "current_version_number": 2}]
        service = ProjectImportService()
        with patch.object(imports, "get_database", return_value=database):
            self.assertEqual(service.list_projects("user")[0]["id"], project_id)
        database.one.return_value = {"current_version_id": "version"}
        database.all.return_value = [{"id": "version", "version_number": 2, "filename": "source.sketch", "source_bytes": 1, "total_bytes": 2, "group_count": 1, "artboard_count": 1, "layer_count": 2, "status": "ready", "created_at": "created", "completed_at": "done", "error_message": None}]
        with patch.object(imports, "get_database", return_value=database):
            self.assertTrue(service.list_versions("user", project_id)[0]["isCurrent"])
        with patch.object(imports, "get_job", return_value={"userId": "other", "id": "job", "stage": "queued", "progress": 5, "message": "waiting"}), self.assertRaises(ApiError):
            service.get_job("user", "job")
        with patch.object(imports, "get_job", return_value={"userId": "user", "id": "job", "stage": "queued", "progress": 5, "message": "waiting"}):
            self.assertEqual(service.get_job("user", "job")["id"], "job")
        database.one.return_value = {"id": project_id}
        with patch.object(imports, "get_database", return_value=database), patch.object(imports, "remove_object_tree") as remove:
            service.delete_project("user", project_id)
        remove.assert_called_once()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            temp_for_job = lambda job_id: root / job_id
            database = Mock()
            submitted = Mock()
            redis = Mock()
            with patch.object(imports, "temp_dir_for_job", side_effect=temp_for_job), patch.object(imports, "get_database", return_value=database), patch.object(imports, "get_redis", return_value=redis), patch.object(imports, "submit_import_job", submitted), patch.object(imports, "iso_now", return_value="now"):
                job = service.queue_import("user", "source.sketch", "", io.BytesIO(b"source"), len(b"source"))
            self.assertEqual(job["stage"], "queued")
            self.assertTrue(submitted.called)

            database = Mock()
            database.one.side_effect = [
                {"id": project_id, "status": "ready"},
                None,
                {"latest_version": 4},
            ]
            submitted = Mock()
            with patch.object(imports, "temp_dir_for_job", side_effect=temp_for_job), patch.object(imports, "get_database", return_value=database), patch.object(imports, "get_redis", return_value=Mock()), patch.object(imports, "submit_import_job", submitted), patch.object(imports, "iso_now", return_value="now"):
                reimport = service.queue_reimport("user", project_id, "next.sketch", io.BytesIO(b"source"), len(b"source"))
            self.assertEqual(reimport["stage"], "queued")


if __name__ == "__main__":
    unittest.main()
