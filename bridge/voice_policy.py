"""Fail-closed policy for tools exposed to voice requests."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Tuple


_ACCESS_MODES = frozenset(("read_only", "scoped_write", "proposal_only"))


@dataclass(frozen=True)
class CapabilityRegistration:
    capability_id: str
    description: str
    tools: Tuple[str, ...]
    access: str
    resource_scope: Tuple[str, ...]
    voice_enabled: bool


class VoicePolicy:
    def __init__(self, registrations: Tuple[CapabilityRegistration, ...]):
        self._registrations = {item.capability_id: item for item in registrations}

    @classmethod
    def from_file(cls, path: Any) -> "VoicePolicy":
        with open(path, "r", encoding="utf-8") as source:
            data = json.load(source)
        entries = data.get("capabilities") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise ValueError("capabilities must be a list")
        registrations = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each capability must be an object")
            capability_id = entry.get("capability_id")
            description = entry.get("description")
            tools = entry.get("tools")
            access = entry.get("access")
            scope = entry.get("resource_scope", [])
            enabled = entry.get("voice_enabled")
            if not isinstance(capability_id, str) or not capability_id:
                raise ValueError("capability_id must be a non-empty string")
            if capability_id in seen:
                raise ValueError("duplicate capability_id: {}".format(capability_id))
            seen.add(capability_id)
            if not isinstance(description, str) or not isinstance(tools, list) or not all(isinstance(t, str) and t for t in tools):
                raise ValueError("description and tools are required")
            if access not in _ACCESS_MODES:
                raise ValueError("unknown access mode: {}".format(access))
            if not isinstance(scope, list) or not all(isinstance(item, str) for item in scope):
                raise ValueError("resource_scope must be a list of strings")
            if not isinstance(enabled, bool):
                raise ValueError("voice_enabled must be a boolean")
            registrations.append(CapabilityRegistration(capability_id, description, tuple(tools), access, tuple(scope), enabled))
        return cls(tuple(registrations))

    def allowed_tools(self) -> FrozenSet[str]:
        return frozenset(tool for item in self._registrations.values() if item.voice_enabled for tool in item.tools)

    def authorize(self, capability_id: str, tool_name: str, operation: str, resource: Optional[str]) -> bool:
        item = self._registrations.get(capability_id)
        if item is None or not item.voice_enabled or tool_name not in item.tools:
            return False
        if operation == "read":
            return True
        if operation != "write" or item.access != "scoped_write" or not resource:
            return False
        normalized = resource.replace("\\", "/").lstrip("/")
        if any(part == ".." for part in normalized.split("/")):
            return False
        return any(normalized.startswith(scope.rstrip("/") + "/") or normalized == scope.rstrip("/") for scope in item.resource_scope if scope)
