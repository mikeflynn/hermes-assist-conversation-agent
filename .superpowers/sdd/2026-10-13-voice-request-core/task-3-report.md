# Task 3 report

- Branch: `feature/voice-requests-handoff`; starting HEAD: `b6b836aba1c34c9afa8c1bad7d9df1be0f0ee5ef`.
- Restored bounded local reads of the known calendar, Things, and news brief paths; no live brief refresh or arbitrary prompt-driven file reads. These cache reads work with an empty policy and do not call the API client. `/api/chat` still returns its HA-facing `reply` field.
- Added `VoicePolicy` evaluation at the routing boundary. Empty and unrelated/unknown registrations deny handoff before any client/session call. Live client creation is deliberately disabled: configured environment values do not prove that the API server uses an explicit restricted tool inventory.
- Handoff is only reported after the injected client's accepted result confirms the same session ID. Verified this with a fake client; no real server, credentials, or live `/v1/runs` traffic was used. No one-shot CLI or direct-agent fallback is reachable from `/api/chat`.
- Preserved the required user constraint verbatim: “HA state control should be caught by HA before sending the request to you so that’s fine.” HA state-control remains outside this voice fallback.
- TDD RED: after adding cache/policy/unavailable-routing tests first, `python3 -m unittest discover -s tests -p 'test_bridge.py' -v` ran 6 tests and failed with 3 expected `AttributeError: module 'bridge.bridge' has no attribute 'route_voice_request'` errors (cache, policy, API-unavailable cases); the existing 3 behaviors passed. This demonstrated the missing routing boundary before implementation.
- GREEN verification (exact requested commands):
  - `python3 -m unittest discover -s tests -p 'test_voice_responses.py' -v` — 2 tests passed.
  - `python3 -m unittest discover -s tests -p 'test_bridge.py' -v` — 7 tests passed.
  - `python3 -m unittest discover -s tests -v` — 36 tests passed.
  - `git diff --check` — clean.
- Remaining external gate: Task 4 must verify the running API server's explicit restricted tool inventory and desktop/session behavior before live handoffs are enabled. No claim is made that a live handoff currently activates.
- Product commit SHA: `2cfd75d9693c10ec4970dbcd1ad8cbc7ff548424` (`fix: close voice routing safety gaps`).

## Fix round 1/5 — review findings

- Added a runtime `HermesApiClient` from `HERMES_API_URL` and `HERMES_API_KEY`; absent inputs leave the client unavailable. Before every non-cache run, route now performs authenticated capability discovery and a strict enabled concrete-tool inventory query, requiring exact equality with `VoicePolicy.allowed_tools()`. Empty policy permits only a no-tools run; inventory mismatch/malformed/API errors prevent session run submission. No live endpoint or credentials were used.
- Added `get_enabled_tool_inventory() -> frozenset[str]` with strict shape/name checks and disposable fake HTTP-server coverage.
- Bounded local confirmed-outcome dedupe to 512 entries/300 seconds and keyed by canonical state path plus request ID, text, and context. Failures are not cached. Generated IDs digest canonical conversation ID, bounded history, and utterance; explicit incoming IDs remain respected. Task 2's session-scoped server idempotency remains the authority for ambiguous retries.
- Actual submit includes current utterance separately as `text` and enforces it in bounded submitted history/context. Handoff still requires accepted status and matching session ID; error speech stays generic.
- TDD RED: new API inventory tests failed because the method was absent; bridge tests exposed the disabled-empty-registry route, cross-state outcome reuse, missing request-ID derivation, and absent context at submit boundary. GREEN after implementation.
- Verification: `test_voice_responses.py` — 2 passed; `test_bridge.py` — 12 passed; `test_hermes_api.py` — 14 passed; full `python3 -m unittest discover -s tests -v` — 43 passed; `git diff --check` — clean. Python 3.9 `py_compile` passed. Test teardown emitted a benign socket ResourceWarning; suite exit was successful.
- Remaining external gate: Task 4 must configure/verify `no_mcp` explicitly before any live tool-enabled handoff. This change does not configure runtime Hermes or claim live handoff availability.
