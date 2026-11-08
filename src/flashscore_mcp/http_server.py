"""Generic IaaS HTTP entrypoint for Streamable HTTP MCP.

Works on Railway, Fly.io, Render, DigitalOcean App Platform, AWS ECS/Fargate,
Google Cloud Run, Azure Container Apps, and any Docker-compatible host.

Also usable as a drop-in alternative to the Apify-specific entrypoint.

Configured for maximum client compatibility (Grok, Claude, Cursor, etc.):
- stateless_http=True  (no sticky session required)
- json_response=True   (direct JSON instead of mandatory SSE)
- CORS exposing Mcp-Session-Id so browser-based / proxy clients work
- Bearer token required (FLASHSCORE_MCP_TOKEN); the process refuses to start without one

Note for Grok / xAI remote MCP:
  Grok prefers (and many remote clients require) HTTPS endpoints.
  Plain http://PUBLIC_IP:8000/mcp may be rejected. Use a TLS reverse proxy
  (Caddy, nginx, Cloudflare Tunnel, ngrok) or a platform that provides HTTPS.
  A Cloudflare Quick Tunnel provides HTTPS, not authentication — clients must
  still send Authorization: Bearer <FLASHSCORE_MCP_TOKEN>.
"""

from __future__ import annotations

import hmac
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
from starlette.responses import JSONResponse

from flashscore_mcp import __version__
from flashscore_mcp.config import settings
from flashscore_mcp.server import mcp

_TOKEN_ENV = "FLASHSCORE_MCP_TOKEN"
_MIN_TOKEN_LEN = 16


def _require_token() -> str:
    token = os.getenv(_TOKEN_ENV, "").strip()
    if len(token) < _MIN_TOKEN_LEN:
        logger.error(
            "{} must be set to a secret of at least {} characters. "
            "Refusing to start an unauthenticated HTTP server.",
            _TOKEN_ENV,
            _MIN_TOKEN_LEN,
        )
        raise SystemExit(1)
    return token


def _bearer_ok(header: str, token: str) -> bool:
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    supplied = parts[1].encode("utf-8")
    expected = token.encode("utf-8")
    if len(supplied) != len(expected):
        return False
    return hmac.compare_digest(supplied, expected)


class BearerAuthMiddleware:
    """Reject every HTTP request except CORS preflight unless the bearer token matches."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self._token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if _bearer_ok(headers.get("authorization", ""), self._token):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {"error": "unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)


def main() -> None:
    """Start the MCP server over Streamable HTTP."""
    token = _require_token()
    port = int(os.getenv("PORT", str(getattr(settings, "port", 8000))))
    host = os.getenv("HOST", getattr(settings, "host", "0.0.0.0"))

    logger.info(
        "Starting Flashscore MCP Server v{} (IaaS / generic HTTP mode) on {}:{}",
        __version__,
        host,
        port,
    )
    logger.info("MCP endpoint will be available at http://{}:{}/mcp", host, port)
    logger.info("HTTP authentication is enabled (bearer token).")
    logger.info(
        "Grok / remote clients: prefer HTTPS. If using plain HTTP IP, connection may be rejected by the client."
    )

    # Build the Streamable HTTP ASGI application from FastMCP.
    # Health (/health) and root (/) routes are registered via @mcp.custom_route
    # on the shared mcp instance (see server.py). Do NOT assign to app.routes
    # — FastMCP's Starlette app makes that attribute read-only / property-backed
    # and previously caused AttributeError crash-loops on the Rumble VM.
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
            ),
            Middleware(BearerAuthMiddleware, token=token),
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
