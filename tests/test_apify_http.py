"""Local battle-test of the Streamable HTTP surface the Apify Actor serves."""
from __future__ import annotations

import unittest

from starlette.testclient import TestClient

from flashscore_mcp.server import mcp

EXPECTED_TOOLS = {
    "list_sports",
    "list_countries",
    "list_leagues",
    "get_standings",
    "get_results_history",
    "get_upcoming_fixtures",
    "get_news",
    "list_archive_seasons",
    "get_league",
    "get_odds",
    "get_historical_standings",
    "get_historical_results",
}


class ApifyHttpCompat(unittest.TestCase):
    def test_health_and_stateless_mcp_handshake(self):
        app = mcp.http_app(
            transport="streamable-http",
            stateless_http=True,
            json_response=True,
        )
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        with TestClient(app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            body = health.json()
            self.assertEqual(body["status"], "ok")
            self.assertEqual(body["mcp_endpoint"], "/mcp")

            initialized = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "battle-test", "version": "0.0.1"},
                    },
                },
                headers=headers,
            )
            self.assertEqual(initialized.status_code, 200)
            self.assertEqual(initialized.headers.get("content-type", "").split(";")[0], "application/json")
            result = initialized.json()["result"]
            self.assertEqual(result["protocolVersion"], "2025-03-26")
            self.assertEqual(result["serverInfo"]["name"], "flashscore-mcp")
            self.assertEqual(result["serverInfo"]["version"], "0.2.3")

            listed = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                headers=headers,
            )
            self.assertEqual(listed.status_code, 200)
            names = {tool["name"] for tool in listed.json()["result"]["tools"]}
            self.assertEqual(names, EXPECTED_TOOLS)


if __name__ == "__main__":
    unittest.main()
