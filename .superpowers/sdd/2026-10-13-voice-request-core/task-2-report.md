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
- `50fdca14b8b442b8b43b41fdca44a3a7ad00a292 feat: add Hermes voice session client`

## Fix round 1 — review findings
- Verified installed source read-only at `~/.hermes/hermes-agent/gateway/platforms/api_server.py` and `api_server_runs.py`: capability endpoints expose `{method,path}`; runs require `input`, accept `session_id`, `conversation_history`, and `instructions`; bounded voice context is serialized as user-role `conversation_history` content, never sent in `instructions` or any system/developer prompt field. Accepted runs return top-level `run_id`, `status`, `replayed`; Idempotency-Key replay returns the original admitted run and a changed-payload reuse returns HTTP 409. `runs_idempotency` is an object whose `supported` member is true.
- TDD RED after adding regressions and before implementation: `python3 -m unittest discover -s tests -p 'test_hermes_api.py' -v` — `Ran 10 tests`; `FAILED (failures=1, errors=4)`. The top-level documented success payload was rejected by four submission cases as `HermesApiError: invalid run response`; invalid capability endpoint was accepted (`AssertionError: HermesApiError not raised`). Captured full output: `/Users/mikeflynn/.hermes/cache/scratch/task2-red.txt`.
- Fixed strict endpoint/method/path and required-feature checks, top-level run response parsing, malformed/HTTP/timeout handling, documented request payload fields, and session-scoped persistent request fingerprints. Client does not locally claim a duplicate is accepted: each attempt goes to the server with the same Idempotency-Key, allowing its atomic replay/conflict contract to resolve cross-client/process retries and fail closed on changed payloads. State updates remain atomic/private (0600); no API key is persisted or returned.
- Final focused: `python3 -m unittest discover -s tests -p 'test_hermes_api.py' -v` — 11 tests passed; `python3 -m unittest discover -s tests -p 'test_voice_state.py' -v` — 2 tests passed.
- Final full suite: `python3 -m unittest discover -s tests -v` — 26 tests passed. Existing `ResourceWarning` messages about unclosed sockets appeared in the full suite; tests still passed. `git diff --check` — exit 0.
- Live gate remains BLOCKED: no API server started/configured, no credentials created/used, and live Desktop visibility/continuability was not tested. This was explicitly excluded by the round instructions.
- Modified only `bridge/hermes_api.py`, `bridge/voice_state.py`, `tests/test_hermes_api.py`, `tests/test_voice_state.py`, and this report. No subagents.
- Fix commit: `30f88abb6b133b6e45ca5d6de253c367c38fe93c fix: address voice request API handoff review`.

## Fix round 2 — scoped replay and context trust boundary
- TDD RED: `python3 -m unittest discover -s tests -p 'test_hermes_api.py' -v` — `Ran 11 tests`; `FAILED (errors=2)`. The durable fake server rejected a repeated request ID in a different session with HTTP 409, demonstrating the global raw-key collision before the implementation change.
- Changed API idempotency keys to a stable SHA-256 digest derived from both session ID and request ID, while preserving `HandoffResult.request_id`. Context now goes only in documented user-role `conversation_history`; no `instructions` are submitted.
- Added a local fake server with a persistent in-test idempotency store. Separate clients replay the original run without duplicate creation; changed payload reuse fails closed; identical IDs across sessions create distinct runs; concurrent separate-client retries replay one run. Regression asserts context's user role and absence of `instructions`.
- Focused GREEN: `python3 -m unittest discover -s tests -p 'test_hermes_api.py' -v` — 11 tests passed; `python3 -m unittest discover -s tests -p 'test_voice_state.py' -v` — 2 tests passed.
- Full GREEN: `python3 -m unittest discover -s tests -v` — 26 tests passed. `ResourceWarning`s for unclosed sockets appeared during/after the suite. `git diff --check` — exit 0.
- Product commit: `e912e8d94c0fc2edd2fcf632dfe17f3bbbc32ce1 fix: isolate voice request idempotency by session`.
- Live Desktop visibility remains unverified/blocked. No API server or configuration was changed; no credentials were created or used, and no live smoke test was performed.
- Modified this round: `bridge/hermes_api.py`, `tests/test_hermes_api.py`, and this report. No subagents used.
