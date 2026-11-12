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
    "get_match",
    "get_live_matches",
    "get_h2h",
    "get_matches_by_day",
    "get_team_form",
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
            self.assertEqual(result["serverInfo"]["version"], "0.2.6")

            listed = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                headers=headers,
            )
            self.assertEqual(listed.status_code, 200)
            tools = listed.json()["result"]["tools"]
            names = {tool["name"] for tool in tools}
            self.assertEqual(names, EXPECTED_TOOLS)
            descriptions = {tool["name"]: tool.get("description") or "" for tool in tools}
            self.assertIn("get_match", descriptions["get_results_history"])
            self.assertIn("list_countries", descriptions["list_sports"])
            self.assertIn("get_match", descriptions["get_live_matches"])
            self.assertIn("match_id", descriptions["get_match"])
            for tool in tools:
                self.assertIn("outputSchema", tool, tool["name"])
                schema = tool["outputSchema"]
                self.assertEqual(schema.get("type"), "object")
                self.assertIn("properties", schema)


class ActorOutputSchema(unittest.TestCase):
    def test_apify_output_schema_is_defined(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        actor = json.loads((root / ".actor" / "actor.json").read_text())
        self.assertEqual(actor.get("output"), "./OUTPUT_SCHEMA.json")
        schema = json.loads((root / ".actor" / "OUTPUT_SCHEMA.json").read_text())
        self.assertEqual(schema["actorOutputSchemaVersion"], 1)
        self.assertIn("mcpEndpoint", schema["properties"])
        self.assertEqual(
            schema["properties"]["mcpEndpoint"]["template"],
            "{{run.containerUrl}}/mcp",
        )
        self.assertEqual(
            schema["properties"]["health"]["template"],
            "{{run.containerUrl}}/health",
        )


if __name__ == "__main__":
    unittest.main()
