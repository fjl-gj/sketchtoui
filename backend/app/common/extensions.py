from minio import Minio
from redis import Redis

from ..config.settings import ROOT_DIR, settings
from .database import Database


database: Database | None = None
redis_client: Redis | None = None
minio_client: Minio | None = None


def initialize_extensions() -> None:
    global database, redis_client, minio_client
    if not settings.database_dsn or not settings.redis_url:
        raise RuntimeError("DATABASE_DSN 和 REDIS_URL 必须在 .env 中配置")
    if not all((settings.minio_endpoint, settings.minio_access_key, settings.minio_secret_key, settings.minio_bucket)):
        raise RuntimeError("MINIO_ENDPOINT、MINIO_ACCESS_KEY、MINIO_SECRET_KEY、MINIO_BUCKET 必须在 .env 中配置")
    database = Database(settings.database_dsn, ROOT_DIR)
    database.initialize()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    redis_client.ping()
    minio_client = Minio(settings.minio_endpoint, access_key=settings.minio_access_key, secret_key=settings.minio_secret_key, secure=settings.minio_secure)
    if not minio_client.bucket_exists(settings.minio_bucket):
        minio_client.make_bucket(settings.minio_bucket)


def get_database() -> Database:
    if database is None:
        raise RuntimeError("数据库尚未初始化")
    return database


def get_redis() -> Redis:
    if redis_client is None:
        raise RuntimeError("Redis 尚未初始化")
    return redis_client


def get_minio() -> Minio:
    if minio_client is None:
        raise RuntimeError("MinIO 尚未初始化")
    return minio_client
