from minio import Minio
from redis import Redis

from ..config.settings import ROOT_DIR, settings
from .cache import MemoryCache
from .database import Database
from .storage import LocalStorage, MinioStorage


database: Database | None = None
cache_client: Redis | MemoryCache | None = None
storage_client: LocalStorage | MinioStorage | None = None


def initialize_extensions() -> None:
    global database, cache_client, storage_client
    if not settings.database_dsn:
        raise RuntimeError("DATABASE_DSN 必须在 .env 中配置")
    if settings.cache_backend not in {"memory", "redis"}:
        raise RuntimeError("CACHE_BACKEND 仅支持 memory 或 redis")
    if settings.storage_backend not in {"local", "minio"}:
        raise RuntimeError("STORAGE_BACKEND 仅支持 local 或 minio")
    if settings.cache_backend == "redis" and not settings.redis_url:
        raise RuntimeError("Redis 模式必须配置 REDIS_URL")
    if settings.storage_backend == "minio" and not all((settings.minio_endpoint, settings.minio_access_key, settings.minio_secret_key, settings.minio_bucket)):
        raise RuntimeError("MinIO 模式必须配置 MINIO_ENDPOINT、MINIO_ACCESS_KEY、MINIO_SECRET_KEY、MINIO_BUCKET")
    if settings.storage_backend == "local" and not settings.local_storage_dir.strip():
        raise RuntimeError("本地存储模式必须配置非空 LOCAL_STORAGE_DIR")
    database = Database(settings.database_dsn, ROOT_DIR)
    database.initialize()
    if settings.cache_backend == "redis":
        cache_client = Redis.from_url(settings.redis_url, decode_responses=True)
        cache_client.ping()
    else:
        cache_client = MemoryCache()
    if settings.storage_backend == "minio":
        client = Minio(settings.minio_endpoint, access_key=settings.minio_access_key, secret_key=settings.minio_secret_key, secure=settings.minio_secure)
        storage_client = MinioStorage(client, settings.minio_bucket)
    else:
        storage_client = LocalStorage(ROOT_DIR / settings.local_storage_dir)


def get_database() -> Database:
    if database is None:
        raise RuntimeError("数据库尚未初始化")
    return database


def get_cache() -> Redis | MemoryCache:
    if cache_client is None:
        raise RuntimeError("缓存尚未初始化")
    return cache_client


def get_storage() -> LocalStorage | MinioStorage:
    if storage_client is None:
        raise RuntimeError("文件存储尚未初始化")
    return storage_client
