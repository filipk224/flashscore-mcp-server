"""Generic IaaS HTTP entrypoint for Streamable HTTP MCP.

Works on Railway, Fly.io, Render, DigitalOcean App Platform, AWS ECS/Fargate,
Google Cloud Run, Azure Container Apps, and any Docker-compatible host.

Also usable as a drop-in alternative to the Apify-specific entrypoint.

Configured for maximum client compatibility (Grok, Claude, Cursor, etc.):
- stateless_http=True  (no sticky session required)
- json_response=True   (direct JSON instead of mandatory SSE)
- CORS exposing Mcp-Session-Id so browser-based / proxy clients work
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the package is importable when running as python -m flashscore_mcp.http_server
# or from /app with PYTHONPATH=/app/src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from loguru import logger
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from flashscore_mcp import __version__
from flashscore_mcp.config import settings
from flashscore_mcp.server import mcp


def main() -> None:
    """Start the MCP server over Streamable HTTP."""
    port = int(os.getenv("PORT", str(getattr(settings, "port", 8000))))
    host = os.getenv("HOST", getattr(settings, "host", "0.0.0.0"))

    logger.info(
        "Starting Flashscore MCP Server v{} (IaaS / generic HTTP mode) on {}:{}",
        __version__,
        host,
        port,
    )
    logger.info("MCP endpoint will be available at http://{}:{}/mcp", host, port)

    # Build the Streamable HTTP ASGI application from FastMCP.
    # stateless_http + json_response maximises compatibility with remote clients
    # (Grok, Claude, Cursor, mcp-remote, etc.) that do not require long-lived
    # SSE sessions or sticky load-balancer affinity.
    app = mcp.http_app(
        transport="streamable-http",
        stateless_http=True,
        json_response=True,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=[
                    "Content-Type",
                    "Accept",
                    "Authorization",
                    "Mcp-Session-Id",
                    "mcp-session-id",
                    "MCP-Protocol-Version",
                    "mcp-protocol-version",
                ],
                expose_headers=[
                    "Mcp-Session-Id",
                    "mcp-session-id",
                ],
                allow_credentials=False,
            )
        ],
    )

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        timeout_keep_alive=75,
        access_log=True,
    )
    server = uvicorn.Server(config)

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")


if __name__ == "__main__":
    main()
