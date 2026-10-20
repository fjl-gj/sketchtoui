from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]


def load_dotenv(path: Path = ROOT_DIR / ".env") -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value


load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_dsn: str = os.getenv("DATABASE_DSN") or os.getenv("MYSQL_DSN", "")
    redis_url: str = os.getenv("REDIS_URL", "")
    cache_backend: str = os.getenv("CACHE_BACKEND", "").strip().lower() or ("redis" if redis_url else "memory")
    app_base_url: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8123").rstrip("/")
    frontend_origins: tuple[str, ...] = tuple(
        origin.strip().rstrip("/")
        for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:8122,http://127.0.0.1:8122").split(",")
        if origin.strip()
    )
    session_days: int = int(os.getenv("SESSION_DAYS", "7"))
    import_max_upload_bytes: int = int(os.getenv("IMPORT_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
    import_max_archive_entries: int = int(os.getenv("IMPORT_MAX_ARCHIVE_ENTRIES", "25000"))
    import_max_archive_file_bytes: int = int(os.getenv("IMPORT_MAX_ARCHIVE_FILE_BYTES", str(100 * 1024 * 1024)))
    import_max_extracted_bytes: int = int(os.getenv("IMPORT_MAX_EXTRACTED_BYTES", str(2 * 1024 * 1024 * 1024)))
    import_max_compression_ratio: int = int(os.getenv("IMPORT_MAX_COMPRESSION_RATIO", "150"))
    import_max_workers: int = int(os.getenv("IMPORT_MAX_WORKERS", "1"))
    email_delivery: str = os.getenv("EMAIL_DELIVERY", "console").lower()
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_sender: str = os.getenv("SMTP_SENDER", "")
    smtp_use_tls: bool = env_bool("SMTP_USE_TLS", True)
    smtp_use_ssl: bool = env_bool("SMTP_USE_SSL", False)
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "")
    minio_secure: bool = env_bool("MINIO_SECURE", False)
    storage_backend: str = os.getenv("STORAGE_BACKEND", "").strip().lower() or ("minio" if minio_endpoint else "local")
    local_storage_dir: str = os.getenv("LOCAL_STORAGE_DIR", "data/storage")
    mcp_host: str = os.getenv("MCP_HOST", "127.0.0.1")
    mcp_port: int = int(os.getenv("MCP_PORT", "8124"))
    mcp_public_url: str = os.getenv("MCP_PUBLIC_URL", "http://127.0.0.1:8124/mcp").rstrip("/")
    mcp_issuer_url: str = os.getenv("MCP_ISSUER_URL", os.getenv("APP_BASE_URL", "http://127.0.0.1:8123")).rstrip("/")
    mcp_rate_limit_per_minute: int = int(os.getenv("MCP_RATE_LIMIT_PER_MINUTE", "600"))
    mcp_global_rate_limit_per_minute: int = int(os.getenv("MCP_GLOBAL_RATE_LIMIT_PER_MINUTE", "6000"))
    mcp_preview_max_dimension: int = int(os.getenv("MCP_PREVIEW_MAX_DIMENSION", "1600"))
    mcp_preview_font_path: str = os.getenv("MCP_PREVIEW_FONT_PATH", "")


settings = Settings()
