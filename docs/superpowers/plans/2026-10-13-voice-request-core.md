# Voice Request Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route non-HA voice requests into a persistent Hermes Voice Requests session with a generic capability policy and truthful spoken outcomes.

**Architecture:** Keep the existing HA integration contract and cache handlers, but replace the bridge's one-shot fallback with a small policy-driven router and authenticated Hermes session client. Configure the API-server voice surface with only registered tools; unsupported/write requests are staged for app continuation, never executed by the voice path.

**Tech Stack:** Python 3.9-compatible bridge, stdlib `unittest`, Hermes API server/session endpoints, JSON capability registry.

**Spec:** `docs/superpowers/specs/2026-10-13-voice-requests-handoff-design.md`

## Global Constraints

- HA continues handling device intents first; current calendar and Things cache behavior remains unchanged.
- Voice may write only inside Obsidian `Agent`; all other writes require Hermes app takeover and approval.
- Unregistered capabilities are unavailable to voice by default; skill prose is not a permission grant.
- Voice replies must clearly distinguish answered, handed off, unsupported, and unavailable/error outcomes.
- No inherited full CLI tools; exclude terminal, arbitrary code execution, broad filesystem writes, and HA control from voice.
- Preserve pre-existing uncommitted changes in `bridge/bridge.py` and `README.md`.

## Review Focus

- API auth/network failure must not be reported as a successful handoff — test in Task 3.
- Duplicate HA retries must not enqueue the same request twice — test in Task 3.
- Long HA history must not truncate the current utterance — test in Task 3.
- API-server sessions must be visible and continuable in this Desktop build — verify in Task 2; if not, stop and revise the design before implementing a UI fallback.
- Pending approval behavior must be surfaced by the Desktop or explicitly fall back to proposal-only handoff — verify in Task 4 using a harmless test tool.
- The API-server platform must not inherit disallowed tools — assert the live tool inventory in Task 4.

---

### Task 1: Capability policy model

**Files:**
- Create: `bridge/voice_policy.py`
- Create: `bridge/voice_capabilities.json`
- Test: `tests/test_voice_policy.py`

**Interfaces:**
- Produces `CapabilityRegistration(capability_id, description, tools, access, resource_scope, voice_enabled)`.
- Produces `VoicePolicy.from_file(path)`, `VoicePolicy.allowed_tools()`, and `VoicePolicy.authorize(capability_id, tool_name, operation, resource)`.
- `access` is one of `read_only`, `scoped_write`, or `proposal_only`; unknown values fail closed.

- [ ] **Step 1: Write failing tests** for JSON loading, duplicate IDs, unknown access modes, disabled capabilities, allowed read, scoped write, out-of-scope write, and unknown capability/tool denial.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_voice_policy.py' -v`** and confirm failures are from the missing policy API.
- [ ] **Step 3: Implement the dataclasses and JSON loader** in `bridge/voice_policy.py`; initialize the registry with no optional external capabilities enabled.
- [ ] **Step 4: Re-run the focused tests** and confirm all policy cases pass.
- [ ] **Step 5: Commit** as `feat: add voice capability policy`.

### Task 2: Hermes API client and persistent Voice Requests session

**Files:**
- Create: `bridge/hermes_api.py`
- Create: `bridge/voice_state.py`
- Test: `tests/test_hermes_api.py`
- Test: `tests/test_voice_state.py`

**Interfaces:**
- `HermesApiClient(base_url, api_key, timeout).get_capabilities()` validates the documented API surface.
- `HermesApiClient.get_or_create_voice_session(state_path) -> str` returns the persistent session ID.
- `HermesApiClient.submit_voice_request(session_id, request_id, text, context) -> HandoffResult` returns confirmed session/handoff identifiers or a typed failure.
- `HandoffResult` carries `status`, `session_id`, `request_id`, and optional `detail`; it never contains the API key.

- [ ] **Step 1: Write failing tests** using a local fake HTTP server for authenticated capability discovery, session reuse/create, request submission, HTTP errors, malformed payloads, timeout, and duplicate request IDs.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_hermes_api.py' -v` and `python3 -m unittest discover -s tests -p 'test_voice_state.py' -v`** and verify the expected missing-interface failures.
- [ ] **Step 3: Inspect the installed Hermes API server's live `/v1/capabilities` and documented session endpoint schemas.** Use only a disposable test session; confirm API-created sessions are visible and continuable in Desktop. Do not send a write-capable tool request during this probe.
- [ ] **Step 4: Implement the client with stdlib HTTP, bearer authentication, bounded response sizes/timeouts, and atomic state-file updates.** Store only the Voice Requests session ID and recent request IDs; create the state file with user-only permissions.
- [ ] **Step 5: Re-run the focused tests** and verify the real disposable-session smoke test.
- [ ] **Step 6: Commit** as `feat: add Hermes voice session client`.

### Task 3: Explicit voice outcomes and idempotent handoff

**Files:**
- Create: `bridge/voice_responses.py`
- Modify: `bridge/bridge.py`
- Modify: `bridge/hermes_api.py` (public enabled-tool inventory check for Task 3 runtime policy enforcement)
- Test: `tests/test_voice_responses.py`
- Test: `tests/test_bridge.py`
- Test: `tests/test_hermes_api.py`

**Interfaces:**
- `VoiceOutcome(status, spoken_reply, request_id=None, session_id=None)` has status `answered`, `handed_off`, `unsupported`, or `unavailable`.
- `format_spoken_reply(outcome) -> str` returns concise speech text.
- The existing `POST /api/chat` response retains the `reply` field consumed by the HA integration; additional fields may be added but are not required by HA.
- `HermesApiClient.get_enabled_tool_inventory() -> frozenset[str]` validates authenticated `GET /v1/toolsets` and returns concrete tools from enabled, enumerable toolsets; malformed or unknown inventory fails closed. Before `POST /v1/runs`, the bridge requires this inventory to equal `VoicePolicy.allowed_tools()` exactly. Task 4 must explicitly disable default MCP inheritance (`no_mcp`) because `/v1/toolsets` does not report default MCP servers.
- Generic Voice Requests session submission is a core transport, not an optional capability. It is permitted only after the tool-inventory gate passes; an empty optional registry permits a no-tools session run but no external tools.

- [ ] **Step 1: Write failing tests** for each outcome, confirmed-vs-failed handoffs, unsupported requests, enabled-tool inventory match/mismatch, duplicate retries versus a later identical utterance, state-path isolation, and actual submitted context preserving the current user text.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_voice_responses.py' -v`, `python3 -m unittest discover -s tests -p 'test_bridge.py' -v`, and `python3 -m unittest discover -s tests -p 'test_hermes_api.py' -v`** and confirm failures identify missing outcome, inventory, idempotency, and routing behavior.
- [ ] **Step 3: Implement the outcome formatter and bridge routing** to keep calendar/Things handling, use the persistent Hermes session, and report handoff only after API confirmation. Treat generic session submission as the core transport; before every run, require the concrete enabled API tool inventory to equal the registered tool names exactly. A missing API server, mismatch, or malformed inventory fails closed; no optional tool is available from an empty registry.
- [ ] **Step 4: Bound request/history/concurrency and deduplication**; derive a stable request identity for retries while distinguishing later identical utterances, key local cache entries by the state/session identity and request, and cap/expire that cache. Retain the current utterance when trimming history and assert at the actual submit boundary that it is present. Do not expose auth headers, secrets, or raw internal exceptions in spoken replies.
- [ ] **Step 5: Run the focused tests and full suite** with `python3 -m unittest discover -s tests -v`.
- [ ] **Step 6: Commit** as `feat: route voice requests to Hermes sessions`.

### Task 4: Runtime configuration and end-to-end compatibility gate

**Files:**
- Modify: `bridge/bridge.py` (runtime configuration validation and fail-closed client construction)
- Modify: `README.md`
- Create: `docs/voice-requests-setup.md`
- Test: `tests/test_voice_config.py`

**Interfaces:**
- Document environment/config inputs: API base URL, API key source, capability registry path, state path, request timeout, and explicitly allowed API-server tools. The API-server platform selection must be explicit and include Hermes' `no_mcp` sentinel; never rely on the API toolsets endpoint alone to report default MCP servers.
- Default configuration denies optional tools and writes; `Agent`-scoped Obsidian access is added only by its separate plan.

- [ ] **Step 1: Write failing config tests** for missing API credentials, unsafe/broad tool selections, missing `no_mcp`, unknown registry entries, and invalid timeouts.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_voice_config.py' -v`** and verify the tests fail because configuration validation is absent.
- [ ] **Step 3: Implement fail-closed configuration validation** and document secure local setup. Do not commit secrets or overwrite existing README edits; patch only the relevant section.
- [ ] **Step 4: Run all tests and `git diff --check`**; inspect the diff to confirm the pre-existing `README.md` and `bridge.py` changes remain intact.
- [ ] **Step 5: Verify manually** that the API-server tool inventory excludes disallowed tools and the effective config contains `no_mcp` so globally enabled MCP servers cannot be inherited; use a harmless approval-gated test tool to confirm pending approval reaches Desktop, or confirm the proposal-only fallback. Verify HA device commands and calendar/Things requests retain their existing paths; verify API-down and unsupported requests produce the right spoken replies.
- [ ] **Step 6: Commit** as `docs: configure voice request handoff`.

## Exit gate

Do not proceed to the capability plans until the persistent session is visible/continuable in the user's Hermes Desktop and the API-server tool inventory is demonstrably restricted. If approval events are not surfaced in Desktop, stop and write a small follow-up design before implementing a custom approval UI.
