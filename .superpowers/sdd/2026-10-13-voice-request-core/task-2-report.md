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

## Fix round 1 — review findings
- Verified installed source read-only at `~/.hermes/hermes-agent/gateway/platforms/api_server.py` and `api_server_runs.py`: capability endpoints expose `{method,path}`; runs require `input`, accept `session_id`, `conversation_history`, and `instructions`; context is now serialized into the documented `instructions` field, never sent as the undocumented `context` field. Accepted runs return top-level `run_id`, `status`, `replayed`; Idempotency-Key replay returns the original admitted run and a changed-payload reuse returns HTTP 409. `runs_idempotency` is an object whose `supported` member is true.
- TDD RED after adding regressions and before implementation: `python3 -m unittest discover -s tests -p 'test_hermes_api.py' -v` — `Ran 10 tests`; `FAILED (failures=1, errors=4)`. The top-level documented success payload was rejected by four submission cases as `HermesApiError: invalid run response`; invalid capability endpoint was accepted (`AssertionError: HermesApiError not raised`). Captured full output: `/Users/mikeflynn/.hermes/cache/scratch/task2-red.txt`.
- Fixed strict endpoint/method/path and required-feature checks, top-level run response parsing, malformed/HTTP/timeout handling, documented request payload fields, and session-scoped persistent request fingerprints. Client does not locally claim a duplicate is accepted: each attempt goes to the server with the same Idempotency-Key, allowing its atomic replay/conflict contract to resolve cross-client/process retries and fail closed on changed payloads. State updates remain atomic/private (0600); no API key is persisted or returned.
- Final focused: `python3 -m unittest discover -s tests -p 'test_hermes_api.py' -v` — 11 tests passed; `python3 -m unittest discover -s tests -p 'test_voice_state.py' -v` — 2 tests passed.
- Final full suite: `python3 -m unittest discover -s tests -v` — 26 tests passed. Existing `ResourceWarning` messages about unclosed sockets appeared in the full suite; tests still passed. `git diff --check` — exit 0.
- Live gate remains BLOCKED: no API server started/configured, no credentials created/used, and live Desktop visibility/continuability was not tested. This was explicitly excluded by the round instructions.
- Modified only `bridge/hermes_api.py`, `bridge/voice_state.py`, `tests/test_hermes_api.py`, `tests/test_voice_state.py`, and this report. No subagents.
- Fix commit: `96417ce8507d10fd4999c5c21dd8b2a9558133c8 fix: address voice request API handoff review`.
