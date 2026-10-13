# Invoice Ninja Voice Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable voice to look up Invoice Ninja records safely and hand off create/update requests to Hermes without making changes from the voice turn.

**Architecture:** Add an Invoice Ninja read-only adapter registered in the generic voice capability policy. Voice mutations produce a structured proposal in the persistent Voice Requests session; the local API is not called for writes during that voice request. Any later write happens only after Mike continues and confirms in Hermes.

**Tech Stack:** Python 3.9-compatible HTTP client, Invoice Ninja local API, Hermes capability registry/session handoff.

**Spec:** `docs/superpowers/specs/2026-10-13-voice-requests-handoff-design.md`

## Global Constraints

- Depends on the completed core handoff plan: `docs/superpowers/plans/2026-10-13-voice-request-core.md`.
- Initial Invoice Ninja voice operations are read-only; no create/update/delete API calls from the voice path.
- Mutations are handed to the Hermes app and require confirmation of the exact record and parameters there.
- API credentials are least-privilege, excluded from logs/prompts/speech, and stored outside the repository.
- Handoffs and later writes use request identity/deduplication; every approved write is read back for verification.

## Review Focus

- Invoice Ninja auth expiry/401 must not cause a false record result — test in Task 1.
- Searches with empty, partial, or ambiguous names must not select a record for mutation — test in Task 2.
- Voice retry/replayed request must not create duplicate proposals or writes — test in Task 2.
- Malicious record text must not alter tool policy or trigger unrelated tools — test in Task 2.
- Read-only credentials/endpoints must be verified; no write HTTP verb may be called from voice — assert in Task 1.

---

### Task 1: Read-only Invoice Ninja client

**Files:**
- Create: `bridge/invoice_ninja_client.py`
- Test: `tests/test_invoice_ninja_client.py`

**Interfaces:**
- `InvoiceNinjaClient(base_url, api_token, timeout)` handles authenticated requests to the configured local instance.
- `search_clients(query, limit=5) -> list[ClientRecord]` and `search_invoices(query, limit=5) -> list[InvoiceRecord]` are read-only.
- Only documented GET endpoints are allowed by the client; all other methods raise `PermissionError`.

- [ ] **Step 1: Write failing tests** against a local fake HTTP server for client/invoice searches, bounded results, auth header, 401, timeout, malformed JSON, and rejection of non-GET methods.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_invoice_ninja_client.py' -v`** and confirm expected missing API behavior.
- [ ] **Step 3: Verify the installed Invoice Ninja API version and local API endpoint shapes** using read-only requests; redact tokens and PII from diagnostic output.
- [ ] **Step 4: Implement the read-only client** with the verified endpoints, bounded responses, and safe typed results.
- [ ] **Step 5: Re-run tests** and verify no mutation method is issued.
- [ ] **Step 6: Commit** as `feat: add read-only Invoice Ninja client`.

### Task 2: Capability registration and handoff behavior

**Files:**
- Create: `bridge/invoice_ninja_tools.py`
- Modify: `bridge/voice_capabilities.json`
- Test: `tests/test_invoice_ninja_voice.py`

**Interfaces:**
- `lookup_invoice_ninja(query, record_type, limit=5)` delegates only to client search functions and returns source-labelled, bounded records.
- `propose_invoice_ninja_change(action, target, fields, request_id)` emits a proposal into the existing Voice Requests session; it does not call Invoice Ninja.

- [ ] **Step 1: Write failing tests** for successful lookup, ambiguous/no-match results, create/update handoff payloads, unsupported mutation, duplicate request IDs, and proof that no write endpoint is called.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_invoice_ninja_voice.py' -v`** and verify the missing functions fail.
- [ ] **Step 3: Implement the read-only tools and proposal-only mutation handler**; register access as `read_only` and `proposal_only`, never as voice write access.
- [ ] **Step 4: Run tests** and verify the exact spoken handoff text and persisted proposal/session identifiers.
- [ ] **Step 5: Commit** as `feat: route Invoice Ninja writes for app review`.

### Task 3: Local integration verification

**Files:**
- Modify: `docs/voice-requests-setup.md`
- Test: `tests/test_invoice_ninja_config.py`

- [ ] **Step 1: Write failing tests** for missing/invalid URL or token, secret redaction, and disabled-by-default capability registration.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_invoice_ninja_config.py' -v`** and verify failures.
- [ ] **Step 3: Add secure configuration and setup instructions** without committing credentials.
- [ ] **Step 4: Run the full suite and perform read-only live lookups** against the user's local instance; verify a voice create/update request appears in Voice Requests while the target record remains unchanged.
- [ ] **Step 5: Commit** as `docs: configure Invoice Ninja voice lookup`.

## Exit gate

Do not add voice-side Invoice Ninja mutations in this plan. Enabling any write tool requires a separate reviewed design that proves app-side approval is enforced and that approval is bound to the exact proposed record and payload.
