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

    def test_denies_unknown_capability_or_tool(self):
        policy = self.load([self.capability()])
        self.assertFalse(policy.authorize("missing", "notes.read", "read", "Agent/a.md"))
        self.assertFalse(policy.authorize("notes", "shell.exec", "read", "Agent/a.md"))


if __name__ == "__main__":
    unittest.main()
