"""Apify Actor entrypoint – runs the Flashscore MCP server over Streamable HTTP.

This is the production entrypoint for Apify Standby mode.
Clients connect to <actor-url>/mcp with a bearer token.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from apify import Actor
from loguru import logger

# Import the existing FastMCP instance and tools from the package
from flashscore_mcp.server import mcp  # the FastMCP object with all tools registered


async def main() -> None:
    async with Actor:
        Actor.log.info("Starting Flashscore MCP Server on Apify (Standby-ready)")

        actor_input = await Actor.get_input() or {}
        idle = actor_input.get("idleTimeoutSecs")
        if idle is not None:
            Actor.log.info(
                "Received input idleTimeoutSecs={}. The platform Standby idle "
                "timeout is set in the Actor Standby settings, not by this process.",
                idle,
            )

        # Same Streamable HTTP flags as the generic IaaS server, so Grok and
        # other remote clients do not need sticky sessions or mandatory SSE.
        app = mcp.http_app(
            transport="streamable-http",
            stateless_http=True,
            json_response=True,
        )

        # Bind to the port Apify expects
        port = Actor.configuration.web_server_port
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            timeout_keep_alive=75,
        )
        web_server = uvicorn.Server(config)

        server_task = asyncio.create_task(web_server.serve())

        url = Actor.configuration.web_server_url
        Actor.log.info(f"MCP server ready at {url}/mcp")
        Actor.log.info("Connect any MCP client (Grok, Claude, Cursor, etc.) to this endpoint.")

        # Keep running until the platform shuts the Actor down
        # (Standby idle timeout or manual abort)
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        finally:
            web_server.should_exit = True
            if not server_task.done():
                await server_task


if __name__ == "__main__":
    asyncio.run(main())
