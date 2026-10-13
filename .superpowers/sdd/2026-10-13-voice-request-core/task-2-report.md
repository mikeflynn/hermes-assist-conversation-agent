# Task 2 report — Hermes API client and persistent Voice Requests session

## Changes
- Added `bridge/hermes_api.py`: stdlib HTTP client, bearer auth, capabilities shape validation, persistent Voice Requests session creation/reuse, `/v1/runs` handoff with `Idempotency-Key`, bounded request/response, typed safe errors, and response validation.
- Added `bridge/voice_state.py`: atomic JSON persistence for session ID and recent request IDs; creates state at mode 0600.
- Added fake-server tests in `tests/test_hermes_api.py` and state tests in `tests/test_voice_state.py`.

## TDD evidence
- RED (as prescribed): focused unittest commands failed to import `bridge.hermes_api` and `bridge.voice_state` (`ModuleNotFoundError`), establishing the missing interfaces.
- GREEN focused: `python3 -m unittest discover -s tests -p 'test_hermes_api.py' -v` — 4 tests passed.
- GREEN focused: `python3 -m unittest discover -s tests -p 'test_voice_state.py' -v` — 2 tests passed.
- Full suite: `python3 -m unittest discover -s tests -v` — 19 tests passed.
- `git diff --check` — exit 0.

## Live gate
- BLOCKED: the installed Hermes API server is not configured/running, and this task has no authorization to enable/configure it or create credentials. Per security gate, no server was started and no live request was made. Desktop session-visibility/continuability smoke test remains BLOCKED pending a restricted API tool allowlist and user authorization.

## Self-review / remaining concern
- API submission dedupe is durable through both server-side `Idempotency-Key` and recently persisted IDs when the client has been initialized with `get_or_create_voice_session`. The durable local duplicate result is an accepted/deduplicated indication without retrieving the earlier run identifier, because the documented contract supplies no run lookup here. The `HandoffResult` reports session/request IDs and server status detail, not the API key.
- No bridge/config changes made. No implementation/reviewer subagents used.

## Commit
- `720b93fe0a4069d8932225c18ed5e6d67674f8f1 feat: add Hermes voice session client`
