from __future__ import annotations

import hashlib
import logging
import time

import anyio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..common.extensions import get_cache


logger = logging.getLogger(__name__)


class McpRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, path: str, per_token_limit: int, global_limit: int) -> None:
        super().__init__(app)
        self.path = path
        self.per_token_limit = max(0, per_token_limit)
        self.global_limit = max(0, global_limit)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path != self.path or (self.per_token_limit == 0 and self.global_limit == 0):
            return await call_next(request)
        allowed, retry_after = await anyio.to_thread.run_sync(self.consume, request.headers.get("authorization", ""))
        if not allowed:
            logger.warning("MCP request rate limited", extra={"path": request.url.path})
            return JSONResponse(
                {"error": "MCP 请求过于频繁，请稍后重试"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    def consume(self, authorization: str) -> tuple[bool, int]:
        now = int(time.time())
        window = now // 60
        retry_after = 60 - now % 60
        keys_and_limits: list[tuple[str, int]] = []
        if self.global_limit:
            keys_and_limits.append((f"mcp:rate:global:{window}", self.global_limit))
        if self.per_token_limit and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
            if token:
                token_id = hashlib.sha256(token.encode("utf-8")).hexdigest()
                keys_and_limits.append((f"mcp:rate:token:{token_id}:{window}", self.per_token_limit))
        if not keys_and_limits:
            return True, retry_after
        pipeline = get_cache().pipeline()
        for key, _limit in keys_and_limits:
            pipeline.incr(key)
            pipeline.expire(key, retry_after + 1)
        results = pipeline.execute()
        counts = results[::2]
        return all(count <= limit for count, (_key, limit) in zip(counts, keys_and_limits)), retry_after
