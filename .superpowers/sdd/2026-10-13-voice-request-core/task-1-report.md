# Task 1 report — Capability policy model

## Files changed
- `bridge/voice_policy.py`: immutable `CapabilityRegistration`, strict JSON loader, enabled-tool listing, and fail-closed authorization. Scoped writes require an explicit resource under a configured scope; traversal segments are denied.
- `bridge/voice_capabilities.json`: empty registry; no optional capabilities enabled.
- `tests/test_voice_policy.py`: eight policy behavior tests.

## TDD evidence
- RED: `python3 -m unittest discover -s tests -p 'test_voice_policy.py' -v` — failed to import `bridge.voice_policy` (`ModuleNotFoundError`), the missing API under test.
- GREEN: same command — all 8 tests passed.
- Full suite: `python3 -m unittest discover -s tests -v` — all 8 tests passed.

## Commit
- `510435f feat: add voice capability policy`

## Self-review
- Unknown IDs, tools, disabled registrations, unknown access modes, unrecognized operations, and out-of-scope writes deny or fail loading.
- `proposal_only` does not authorize writes; empty resource scope cannot authorize writes.
- Existing bridge/README changes were untouched.

## Concerns
- Scope values are interpreted as resource path prefixes. Adapters remain responsible for providing canonical resource identifiers and enforcing the same boundary at the actual tool operation.
- `read` is allowed for any registered tool regardless of access mode; this supports read-only portions of scoped-write and proposal-only registrations.

## Fix-round 1 — review findings

### Changes
- `bridge/voice_policy.py`: canonicalize scope and resource paths using path components; accept repeated separators and harmless `.` segments in configured scopes, but reject absolute paths and traversal/dot components in resources. Authorization is component-prefix based, not string-prefix based. Registry validation now rejects blank descriptions, empty/duplicate/invalid tool lists, malformed access values and scopes, and empty scopes for `scoped_write`.
- `tests/test_voice_policy.py`: added regression coverage for path normalization/traversal/absolute paths, invalid operations/resources, malformed registry shapes, blank descriptions, duplicate tools, and unsafe/empty scopes.

### TDD evidence
- RED command: `python3 -m unittest discover -s tests -p 'test_voice_policy.py' -v`
- RED result: failed as expected on the new assertions: 8 failures and 1 error across new cases (including a traceback on integer `resource`, missing `ValueError` for blank description/duplicate tools/unsafe scopes, and failure to match normalized scope `Agent//./`).
- GREEN focused command: `python3 -m unittest discover -s tests -p 'test_voice_policy.py' -v` — `Ran 13 tests ... OK`.
- Full command: `python3 -m unittest discover -s tests -v` — `Ran 13 tests ... OK`.
- Hygiene: `git diff --check` — exit 0.

### Commit
- `f56715ea53dde6c08a161c04c9a6fb617412e129 fix: harden voice capability authorization`

## Fix-round 2 — Windows drive-qualified path bypass

### Changes
- `bridge/voice_policy.py`: reject paths whose first two characters are an ASCII/Unicode alphabetic drive letter and colon, covering both drive-absolute (`C:\\Agent`) and drive-qualified (`C:Agent`) forms. The shared path-component validator applies this to configured scopes and requested resources.
- `tests/test_voice_policy.py`: add both forms to scope-rejection tests and assert write authorization denies both forms as resources.

### TDD evidence
- RED command: `python3 -m unittest discover -s tests -p 'test_voice_policy.py' -v`
- RED output (exit 1):
```text
test_allows_read_for_registered_tool (test_voice_policy.VoicePolicyTests) ... ok
test_allows_write_within_scope (test_voice_policy.VoicePolicyTests) ... ok
test_denies_invalid_operation_and_resource_types (test_voice_policy.VoicePolicyTests) ... ok
test_denies_unknown_capability_or_tool (test_voice_policy.VoicePolicyTests) ... ok
test_denies_write_outside_scope (test_voice_policy.VoicePolicyTests) ... ok
test_disabled_capability_is_denied (test_voice_policy.VoicePolicyTests) ... ok
test_loads_registry_and_lists_only_enabled_tools (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_duplicate_capability_ids (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_empty_description_and_duplicate_tool_names (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_malformed_registry_shapes (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_unknown_access_mode (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_unsafe_scopes_and_empty_scoped_write_scope (test_voice_policy.VoicePolicyTests) ... test_scope_uses_canonical_components_and_rejects_unsafe_paths (test_voice_policy.VoicePolicyTests) ... ok

======================================================================
FAIL: test_rejects_unsafe_scopes_and_empty_scoped_write_scope (test_voice_policy.VoicePolicyTests) (scope=['C:\\\\Agent'])
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/mikeflynn/Code/worktrees/hermes-assist-conversation-agent/tests/test_voice_policy.py", line 78, in test_rejects_unsafe_scopes_and_empty_scoped_write_scope
    self.load([self.capability(resource_scope=scope)])
AssertionError: ValueError not raised

======================================================================
FAIL: test_rejects_unsafe_scopes_and_empty_scoped_write_scope (test_voice_policy.VoicePolicyTests) (scope=['C:Agent'])
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/mikeflynn/Code/worktrees/hermes-assist-conversation-agent/tests/test_voice_policy.py", line 78, in test_rejects_unsafe_scopes_and_empty_scoped_write_scope
    self.load([self.capability(resource_scope=scope)])
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 13 tests in 0.008s

FAILED (failures=2)
```
- Focused GREEN command: `python3 -m unittest discover -s tests -p 'test_voice_policy.py' -v`
- Focused GREEN output (exit 0):
```text
test_allows_read_for_registered_tool (test_voice_policy.VoicePolicyTests) ... ok
test_allows_write_within_scope (test_voice_policy.VoicePolicyTests) ... ok
test_denies_invalid_operation_and_resource_types (test_voice_policy.VoicePolicyTests) ... ok
test_denies_unknown_capability_or_tool (test_voice_policy.VoicePolicyTests) ... ok
test_denies_write_outside_scope (test_voice_policy.VoicePolicyTests) ... ok
test_disabled_capability_is_denied (test_voice_policy.VoicePolicyTests) ... ok
test_loads_registry_and_lists_only_enabled_tools (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_duplicate_capability_ids (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_empty_description_and_duplicate_tool_names (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_malformed_registry_shapes (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_unknown_access_mode (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_unsafe_scopes_and_empty_scoped_write_scope (test_voice_policy.VoicePolicyTests) ... ok
test_scope_uses_canonical_components_and_rejects_unsafe_paths (test_voice_policy.VoicePolicyTests) ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.008s

OK
```
- Full unittest discovery command: `python3 -m unittest discover -s tests -v`
- Full unittest discovery output (exit 0):
```text
test_allows_read_for_registered_tool (test_voice_policy.VoicePolicyTests) ... ok
test_allows_write_within_scope (test_voice_policy.VoicePolicyTests) ... ok
test_denies_invalid_operation_and_resource_types (test_voice_policy.VoicePolicyTests) ... ok
test_denies_unknown_capability_or_tool (test_voice_policy.VoicePolicyTests) ... ok
test_denies_write_outside_scope (test_voice_policy.VoicePolicyTests) ... ok
test_disabled_capability_is_denied (test_voice_policy.VoicePolicyTests) ... ok
test_loads_registry_and_lists_only_enabled_tools (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_duplicate_capability_ids (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_empty_description_and_duplicate_tool_names (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_malformed_registry_shapes (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_unknown_access_mode (test_voice_policy.VoicePolicyTests) ... ok
test_rejects_unsafe_scopes_and_empty_scoped_write_scope (test_voice_policy.VoicePolicyTests) ... ok
test_scope_uses_canonical_components_and_rejects_unsafe_paths (test_voice_policy.VoicePolicyTests) ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.008s

OK
```
- Hygiene: `git diff --check` — exit 0.

### Commit
- `ffc93a26bda54735a176a551169f76b79d05d6e6 fix: reject drive-qualified voice resource paths`

### Concerns
- This rejects any alphabetic drive-prefix form before path parsing; no OS-specific path library is used, preserving Python 3.9 compatibility.

