import json
import os
import tempfile
import unittest
from unittest.mock import patch

from bridge import bridge


class VoiceConfigTests(unittest.TestCase):
    def env(self, **values):
        base = {"HERMES_API_URL": "http://localhost:8642", "HERMES_API_KEY": "not-a-real-key"}
        base.update(values)
        return patch.dict(os.environ, base, clear=True)

    def test_missing_credentials_disable_client(self):
        with self.env(HERMES_API_KEY=""):
            self.assertIsNone(bridge.get_voice_client())

    def test_rejects_urls_outside_loopback(self):
        for url in ("http://example.com", "https://192.0.2.4"):
            with self.subTest(url=url), self.env(HERMES_API_URL=url):
                self.assertIsNone(bridge.get_voice_client())

    def test_rejects_url_userinfo_query_and_fragment(self):
        for suffix in ("user@localhost", "localhost?token=x", "localhost#fragment", "localhost?", "localhost#"):
            with self.subTest(suffix=suffix), self.env(HERMES_API_URL="http://" + suffix):
                self.assertIsNone(bridge.get_voice_client())

    def test_requires_exactly_no_mcp_config(self):
        for toolsets in (None, ["filesystem"], ["no_mcp", "hermes-api-server"], ["no_mcp", "terminal"]):
            with self.subTest(toolsets=toolsets), self.env(), patch.object(bridge, "_configured_api_toolsets", return_value=toolsets):
                self.assertIsNone(bridge.get_voice_client())
        with self.env(), patch.object(bridge, "_configured_api_toolsets", return_value=["no_mcp"]):
            self.assertIsNotNone(bridge.get_voice_client())

    def test_registry_is_empty_by_default_and_unreadable_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as home, self.env(HERMES_HOME=home):
            with patch.object(bridge, "_configured_api_toolsets", return_value=["no_mcp"]):
                self.assertEqual(bridge.get_voice_policy().allowed_tools(), frozenset())
                self.assertIsNotNone(bridge.get_voice_client())
        with tempfile.TemporaryDirectory() as home, self.env(HERMES_HOME=home, HERMES_VOICE_POLICY_FILE=os.path.join(home, "missing.json")):
            with patch.object(bridge, "_configured_api_toolsets", return_value=["no_mcp"]):
                self.assertIsNone(bridge.get_voice_client())

    def test_invalid_timeout_disables_client(self):
        for timeout in ("0", "31", "soon"):
            with self.subTest(timeout=timeout), self.env(HERMES_API_TIMEOUT_SECONDS=timeout), patch.object(bridge, "_configured_api_toolsets", return_value=["no_mcp"]):
                self.assertIsNone(bridge.get_voice_client())

    def test_valid_configuration_constructs_client_with_timeout_and_profile_state(self):
        with tempfile.TemporaryDirectory() as home, self.env(HERMES_HOME=home, HERMES_API_TIMEOUT_SECONDS="7"):
            with patch.object(bridge, "_configured_api_toolsets", return_value=["no_mcp"]):
                client = bridge.get_voice_client()
                self.assertEqual(client.timeout, 7)
                self.assertEqual(bridge.voice_state_path(), os.path.join(home, "voice_requests_state.json"))
                self.assertEqual(bridge.voice_policy_path(), "")

    def test_explicit_unsafe_tool_selection_is_rejected(self):
        with self.env(HERMES_ASSIST_TOOLSETS="filesystem,terminal"), patch.object(bridge, "_configured_api_toolsets", return_value=["no_mcp"]):
            self.assertIsNone(bridge.get_voice_client())

    def test_read_only_config_lookup_parses_only_explicit_list(self):
        with patch.object(bridge.subprocess, "run", return_value=type("Result", (), {"returncode": 0, "stdout": '["no_mcp"]', "stderr": ""})()):
            self.assertEqual(bridge._configured_api_toolsets(), ["no_mcp"])
        with patch.object(bridge.subprocess, "run", return_value=type("Result", (), {"returncode": 0, "stdout": "null", "stderr": ""})()):
            self.assertIsNone(bridge._configured_api_toolsets())

    def test_state_path_falls_back_only_when_home_is_unset(self):
        with self.env():
            self.assertEqual(bridge.voice_state_path(), os.path.join(os.path.expanduser("~"), ".hermes", "voice_requests_state.json"))
        with self.env(HERMES_HOME="/profile", HERMES_VOICE_STATE_PATH="~/custom-state.json"):
            self.assertEqual(bridge.voice_state_path(), os.path.expanduser("~/custom-state.json"))

    def test_unknown_registry_entry_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            policy_path = os.path.join(directory, "policy.json")
            with open(policy_path, "w", encoding="utf-8") as target:
                json.dump({"capabilities": [{"capability_id": "unknown", "description": "unknown", "tools": ["tool"], "access": "omniscient", "voice_enabled": True}]}, target)
            with self.env(HERMES_VOICE_POLICY_FILE=policy_path), patch.object(bridge, "_configured_api_toolsets", return_value=["no_mcp"]):
                self.assertIsNone(bridge.get_voice_client())


if __name__ == "__main__":
    unittest.main()
