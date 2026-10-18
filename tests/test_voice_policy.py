import json
import tempfile
import unittest
from pathlib import Path

from bridge.voice_policy import VoicePolicy


class VoicePolicyTests(unittest.TestCase):
    def load(self, capabilities):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "capabilities.json"
        path.write_text(json.dumps({"capabilities": capabilities}), encoding="utf-8")
        return VoicePolicy.from_file(path)

    def capability(self, **overrides):
        value = {
            "capability_id": "notes",
            "description": "Notes access",
            "tools": ["notes.read", "notes.write"],
            "access": "scoped_write",
            "resource_scope": ["Agent/"],
            "voice_enabled": True,
        }
        value.update(overrides)
        return value

    def test_loads_registry_and_lists_only_enabled_tools(self):
        policy = self.load([self.capability(), self.capability(capability_id="off", voice_enabled=False)])
        self.assertEqual(policy.allowed_tools(), {"notes.read", "notes.write"})

    def test_voice_handoff_marker_is_not_part_of_api_tool_allowlist(self):
        policy = self.load([
            self.capability(capability_id="voice_handoff", tools=["hermes_api"], access="proposal_only", resource_scope=[]),
            self.capability(capability_id="home_assistant", tools=["ha_get_state"], access="direct_tool_access", resource_scope=[]),
        ])
        self.assertEqual(policy.allowed_tools(), {"ha_get_state"})
        self.assertTrue(policy.authorize("voice_handoff", "hermes_api", "read", None))
        self.assertTrue(policy.authorize("home_assistant", "ha_get_state", "execute", None))
        self.assertFalse(policy.authorize("home_assistant", "ha_get_state", "write", "somewhere"))

    def test_voice_capabilities_registry_matches_approved_api_tools(self):
        registry = Path(__file__).resolve().parents[1] / "bridge" / "voice_capabilities.json"
        policy = VoicePolicy.from_file(registry)
        self.assertEqual(policy.allowed_tools(), {
            "ha_call_service", "ha_get_state", "ha_list_entities", "ha_list_services",
            "conduit_call_user", "conduit_call_watch", "conduit_settings", "conduit_watch_report",
            "web_search", "web_extract",
        })
        for tool in ("web_search", "web_extract"):
            self.assertTrue(policy.authorize("web_search", tool, "read", None))
            self.assertFalse(policy.authorize("web_search", tool, "execute", None))
            self.assertFalse(policy.authorize("web_search", tool, "write", None))

    def test_rejects_duplicate_capability_ids(self):
        with self.assertRaises(ValueError):
            self.load([self.capability(), self.capability()])

    def test_rejects_unknown_access_mode(self):
        with self.assertRaises(ValueError):
            self.load([self.capability(access="unrestricted")])

    def test_disabled_capability_is_denied(self):
        policy = self.load([self.capability(voice_enabled=False)])
        self.assertFalse(policy.authorize("notes", "notes.read", "read", "Agent/today.md"))

    def test_allows_read_for_registered_tool(self):
        policy = self.load([self.capability()])
        self.assertTrue(policy.authorize("notes", "notes.read", "read", "elsewhere.md"))

    def test_allows_write_within_scope(self):
        policy = self.load([self.capability()])
        self.assertTrue(policy.authorize("notes", "notes.write", "write", "Agent/today.md"))

    def test_denies_write_outside_scope(self):
        policy = self.load([self.capability()])
        self.assertFalse(policy.authorize("notes", "notes.write", "write", "elsewhere.md"))

    def test_scope_uses_canonical_components_and_rejects_unsafe_paths(self):
        policy = self.load([self.capability(resource_scope=["Agent//./"])])
        self.assertTrue(policy.authorize("notes", "notes.write", "write", "Agent/today.md"))
        for resource in ("Agentish/today.md", "/Agent/today.md", "Agent/../elsewhere.md", "Agent//../elsewhere.md", "Agent\\..\\elsewhere.md", "Agent/./today.md", "C:\\Agent\\today.md", "C:Agent/today.md", ""):
            with self.subTest(resource=resource):
                self.assertFalse(policy.authorize("notes", "notes.write", "write", resource))

    def test_denies_invalid_operation_and_resource_types(self):
        policy = self.load([self.capability()])
        for operation, resource in (("delete", "Agent/a.md"), ("WRITE", "Agent/a.md"), ("write", None), ("write", 42)):
            with self.subTest(operation=operation, resource=resource):
                self.assertFalse(policy.authorize("notes", "notes.write", operation, resource))

    def test_rejects_empty_description_and_duplicate_tool_names(self):
        for override in ({"description": "  "}, {"tools": ["notes.read", "notes.read"]}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.load([self.capability(**override)])

    def test_rejects_unsafe_scopes_and_empty_scoped_write_scope(self):
        for scope in ([""], ["/Agent"], ["C:\\Agent"], ["C:Agent"], ["Agent/../outside"], ["Agent\\..\\outside"], []):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                self.load([self.capability(resource_scope=scope)])

    def test_rejects_malformed_registry_shapes(self):
        for capabilities in (None, {}, "not-a-list", [None], [self.capability(tools="notes.read")], [self.capability(resource_scope=[None])]):
            with self.subTest(capabilities=capabilities), self.assertRaises(ValueError):
                self.load(capabilities)

    def test_denies_unknown_capability_or_tool(self):
        policy = self.load([self.capability()])
        self.assertFalse(policy.authorize("missing", "notes.read", "read", "Agent/a.md"))
        self.assertFalse(policy.authorize("notes", "shell.exec", "read", "Agent/a.md"))


if __name__ == "__main__":
    unittest.main()
