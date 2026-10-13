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
- `7d53f406c990d17f7c9a00307a3d2662316da635 fix: harden voice capability authorization`

