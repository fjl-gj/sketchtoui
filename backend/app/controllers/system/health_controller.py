from flask import Blueprint

from ...config.settings import settings


health_bp = Blueprint("health", __name__)


@health_bp.get("/api/health")
def health():
    database_backend = "sqlite" if settings.database_dsn.startswith("sqlite:") else "mysql"
    return {"status": "ok", "databaseBackend": database_backend, "storageBackend": "minio", "minioBucket": settings.minio_bucket}
