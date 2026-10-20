from __future__ import annotations

import argparse

import uvicorn

from app.common.extensions import initialize_extensions
from app.config.settings import settings
from app.mcp.server import create_mcp_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SketchToUI Remote MCP server.")
    parser.add_argument("--host", default=settings.mcp_host)
    parser.add_argument("--port", type=int, default=settings.mcp_port)
    args = parser.parse_args()
    initialize_extensions()
    print(f"SketchToUI Remote MCP server running at http://{args.host}:{args.port}/mcp")
    uvicorn.run(create_mcp_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
