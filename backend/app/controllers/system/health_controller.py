from flask import Blueprint

from ...config.settings import settings


health_bp = Blueprint("health", __name__)


@health_bp.get("/api/health")
def health():
    database_backend = "sqlite" if settings.database_dsn.startswith("sqlite:") else "mysql"
    result = {"status": "ok", "databaseBackend": database_backend, "cacheBackend": settings.cache_backend, "storageBackend": settings.storage_backend}
    if settings.storage_backend == "minio":
        result["minioBucket"] = settings.minio_bucket
    return result
