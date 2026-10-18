"""Fail-closed policy for tools exposed to voice requests."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Tuple


_ACCESS_MODES = frozenset(("read_only", "scoped_write", "proposal_only", "direct_tool_access"))


def _path_components(value: str, allow_dot: bool = False) -> Tuple[str, ...]:
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == ":"):
        raise ValueError("absolute or drive-qualified paths are not allowed")
    parts = tuple(part for part in normalized.split("/") if part)
    if any(part == ".." or (part == "." and not allow_dot) for part in parts):
        raise ValueError("unsafe path component")
    return tuple(part for part in parts if part != ".")


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
            if not isinstance(capability_id, str) or not capability_id.strip():
                raise ValueError("capability_id must be a non-empty string")
            if capability_id in seen:
                raise ValueError("duplicate capability_id: {}".format(capability_id))
            seen.add(capability_id)
            if not isinstance(description, str) or not description.strip() or not isinstance(tools, list) or not tools or not all(isinstance(t, str) and t.strip() for t in tools):
                raise ValueError("description and tools are required")
            if len(set(tools)) != len(tools):
                raise ValueError("duplicate tool name")
            if not isinstance(access, str) or access not in _ACCESS_MODES:
                raise ValueError("unknown access mode: {}".format(access))
            if not isinstance(scope, list) or not all(isinstance(item, str) for item in scope):
                raise ValueError("resource_scope must be a list of strings")
            canonical_scope = []
            for value in scope:
                components = _path_components(value, allow_dot=True)
                if not components:
                    raise ValueError("resource_scope entries must be non-empty relative paths")
                canonical_scope.append(components)
            if access == "scoped_write" and not canonical_scope:
                raise ValueError("scoped_write requires a non-empty resource_scope")
            if access == "direct_tool_access" and canonical_scope:
                raise ValueError("direct_tool_access does not use resource_scope")
            if capability_id == "voice_handoff" and (tuple(tools) != ("hermes_api",) or access != "proposal_only" or canonical_scope):
                raise ValueError("voice_handoff must be a proposal_only hermes_api transport capability")
            if not isinstance(enabled, bool):
                raise ValueError("voice_enabled must be a boolean")
            registrations.append(CapabilityRegistration(capability_id, description, tuple(tools), access, tuple(canonical_scope), enabled))
        return cls(tuple(registrations))

    def allowed_tools(self) -> FrozenSet[str]:
        return frozenset(
            tool
            for item in self._registrations.values()
            if item.voice_enabled
            for tool in item.tools
            if not (item.capability_id == "voice_handoff" and tool == "hermes_api")
        )

    def authorize(self, capability_id: str, tool_name: str, operation: str, resource: Optional[str]) -> bool:
        item = self._registrations.get(capability_id)
        if item is None or not item.voice_enabled or tool_name not in item.tools:
            return False
        if operation == "read":
            return True
        if operation == "execute":
            return item.access == "direct_tool_access"
        if operation != "write" or item.access != "scoped_write" or not isinstance(resource, str) or not resource:
            return False
        try:
            components = _path_components(resource)
        except ValueError:
            return False
        return any(components[:len(scope)] == scope for scope in item.resource_scope)
