from __future__ import annotations

import mimetypes
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from minio import Minio
from minio.error import S3Error


def content_type_for(object_name: str) -> str:
    return mimetypes.guess_type(object_name)[0] or "application/octet-stream"


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_name: str) -> Path:
        parts = object_name.split("/")
        if (not object_name or "\\" in object_name or PurePosixPath(object_name).is_absolute()
                or PureWindowsPath(object_name).drive or any(part in {"", ".", ".."} for part in parts)):
            raise ValueError("Invalid storage object name")
        path = self.root.joinpath(*parts).resolve()
        if self.root not in path.parents:
            raise ValueError("Storage object must stay inside LOCAL_STORAGE_DIR")
        return path

    def put_file(self, object_name: str, source: Path) -> None:
        target = self._path(object_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def read_object(self, object_name: str) -> tuple[bytes, str]:
        path = self._path(object_name)
        if not path.is_file():
            raise FileNotFoundError(object_name)
        return path.read_bytes(), content_type_for(object_name)

    def delete_prefix(self, prefix: str) -> None:
        target = self._path(prefix)
        if target.is_dir():
            shutil.rmtree(target)


class MinioStorage:
    def __init__(self, client: Minio, bucket: str) -> None:
        self.client = client
        self.bucket = bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)

    def put_file(self, object_name: str, source: Path) -> None:
        self.client.fput_object(self.bucket, object_name, str(source), content_type=content_type_for(object_name))

    def read_object(self, object_name: str) -> tuple[bytes, str]:
        try:
            response = self.client.get_object(self.bucket, object_name)
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise FileNotFoundError(object_name) from error
            raise
        try:
            return response.read(), response.headers.get("Content-Type", content_type_for(object_name))
        finally:
            response.close()
            response.release_conn()

    def delete_prefix(self, prefix: str) -> None:
        for item in self.client.list_objects(self.bucket, prefix=f"{prefix}/", recursive=True):
            self.client.remove_object(self.bucket, item.object_name)
