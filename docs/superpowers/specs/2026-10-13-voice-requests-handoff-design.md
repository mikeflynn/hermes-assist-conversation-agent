# Voice Requests Handoff — Design

**Status:** Proposed design; implementation not yet approved.

## Goal

Extend the existing Home Assistant (HA) voice path so Mike can ask for work beyond the existing calendar/Things briefs and device-control routing, while handing advanced or unsupported tasks into a dedicated Hermes app session for follow-up. The architecture must support future capabilities without feature-specific changes to the HA bridge each time, and must make voice responses explicit about what it can do, cannot do, or has handed off.

## User-approved constraints

- HA should continue handling its own device state/control intents before sending unmatched requests to Hermes.
- Existing calendar and Things cache-backed behavior remains intact.
- Advanced requests appear in a dedicated **Voice Requests** session in the Hermes app.
- Voice-originated requests must not perform external/system writes. The explicit exception is Obsidian: voice may read and write within the vault's `Agent` folder and may read (but not write) elsewhere in the vault. Destructive Obsidian actions and writes outside `Agent` require Hermes app follow-up and approval.
- Future capabilities should be registered through a generic policy/capability mechanism rather than hard-coded into the bridge.
- Spoken replies should clearly distinguish completed answers, unsupported requests, and work that needs the Hermes session or user approval.

## Current state

The HA custom conversation integration forwards text to `bridge.py` at `/api/chat` and returns its `reply` text to Assist. The bridge currently runs a one-shot `hermes chat -q` call by default, not a persistent Hermes app session. It has no generic handoff/session routing. The local API server setting was not present at inspection time. The bridge's current empty `HERMES_ASSIST_TOOLSETS` means the CLI path inherits normal Hermes CLI tools; this is too broad for a voice-only trust boundary. There are pre-existing uncommitted changes in `bridge/bridge.py` and `README.md`; implementation must preserve them and avoid staging them accidentally.

## Proposed architecture

### Request flow

1. HA retains first opportunity to handle device intents. The current calendar/Things brief logic remains unchanged.
2. The bridge classifies the remaining request using registered capability metadata and a conservative default policy. It must not infer permission from a skill description or model-generated reasoning alone.
3. The bridge returns one of a small explicit set of outcomes:
   - **Answered:** a registered read-only capability completed the request.
   - **Handed off:** the request is represented in the dedicated Voice Requests Hermes session and needs attention there.
   - **Unsupported:** no registered capability can handle it; the spoken response says so plainly and may offer the Hermes session as the next step.
   - **Unavailable/error:** the handoff or capability failed; the response must not imply success.
4. The Hermes session stores enough context to pick up the request. Use a persistent session identifier and concise transcript/context; avoid sending unrelated HA history or secrets.
5. For write-capable work outside the scoped Obsidian `Agent` exception, the voice-originated turn may prepare a proposal but cannot execute the mutation. Mike continues in the Hermes app and explicitly confirms the exact action there. Approval is bound to the displayed operation and parameters, not a generic or ambiguous spoken confirmation.

### Capability and policy registry

Keep voice routing independent from individual feature implementations. A capability registration declares:

- stable capability ID and human-readable description;
- backing skill/tool/integration;
- permitted operation class (read-only, proposal-only, or write-capable);
- accessible resource scope and required credentials;
- voice eligibility and handoff behavior;
- required approval mode for mutations.

Capabilities not explicitly registered are unavailable to voice by default. New capabilities that use existing tools should be configurable/registrable without editing the bridge. A genuinely new service still requires a one-time adapter/tool integration plus its policy entry; it must not silently become voice-enabled. Skill prose is not a permission grant.

### Hermes session and approvals

Use Hermes' supported API/session mechanism rather than spawning a new unrelated one-shot chat for each request. First verify that API-originated sessions appear in the user's Desktop session list and can be continued there. Also verify the behavior of pending approvals in the installed Desktop version.

If the existing Desktop does not surface the required approval event, implement a minimal app-side review surface or use a proposal-only handoff that requires Mike to initiate the write after taking over. Do not substitute prompt instructions for an enforced write boundary. Do not configure unattended approval for the voice-originated path.

### Initial capability scope

- Existing Things/calendar briefs: preserve current behavior.
- Home Assistant device commands: remain with HA's own intent handling; do not expose additional device-control capability through this voice fallback.
- Web search: registered read-only capability.
- Obsidian: voice may read/write only within the `Agent` folder; voice may read-only access the rest of the vault. Write tools must enforce the path boundary, not merely rely on prompt instructions. Deletion and bulk destructive operations remain approval-gated.
- Invoice Ninja: begin with read-only lookup. Mutations remain blocked in the voice-originated turn until app takeover/approval. Use a narrowly scoped API credential and verify writes by reading the exact record back after approved execution.

## Voice response behavior

Responses must be concise and speech-friendly, and state what happens next. Examples (wording may vary):

- Read-only success: “I found the client record. I’ve sent the details to your Hermes session.”
- Needs app follow-up: “I can prepare that, but it needs to be handled in the Voice Requests session. I haven’t changed anything.”
- Unsupported: “I can’t do that from the voice assistant. I haven’t taken action.”
- Handoff failed: “I couldn’t send that to Hermes, so nothing was started.”

Only say a request was handed off after the session write is confirmed. Never describe a proposed operation as completed. If capability classification is uncertain, default to a clear handoff or unsupported response, not a mutation.

## Security and operational requirements

- Voice-originated tools are allowlisted; no inherited full CLI defaults. Exclude terminal, arbitrary code execution, and broad filesystem writes. The currently approved voice API inventory is limited to the exact Home Assistant and Conduit tools registered in `bridge/voice_capabilities.json`; additions require explicit policy authorization and a matching live-inventory check.
- Obsidian access is path-scoped: read/write in `Agent`, read-only elsewhere, and destructive operations approval-gated. Enforce this in the tool/adapter itself. Invoice Ninja reads/writes use separate least-privilege credentials where supported.
- Keep API keys out of prompts, logs, and speech. Authenticate bridge-to-Hermes API calls; bind services to trusted interfaces and use TLS/access controls when traffic crosses an untrusted network.
- Preserve request IDs and use idempotency/deduplication for handoffs and later writes to prevent retries from creating duplicate records.
- Bound request length, history, concurrency, and runtime. Ensure truncation cannot remove the user's current request while retaining stale history.
- Keep an audit trail of handoff ID, session ID, capability, proposal, approval outcome, and resulting record ID without logging credentials or unnecessary transcript content.

## Alternatives considered

1. **Generic registry plus persistent session and approval flow (recommended):** supports future services and a consistent user experience, with more initial integration work and a required verification of Desktop/API approval behavior.
2. **Feature-specific routing in `bridge.py`:** quicker initially but makes every new capability a bridge code change and encourages policy drift; rejected.
3. **Only emit a notification/request summary:** safer and simpler but does not provide the requested persistent, actionable Hermes thread; fallback only if session/approval integration proves unavailable.

## Verification and acceptance criteria

- HA device intents and current Things/calendar responses still take their existing paths.
- A registered web-search request and Obsidian reads succeed through voice; voice can create/update notes only inside `Agent`, and cannot write elsewhere in the vault.
- A request for an Invoice Ninja create/update is handed off; the record remains unchanged until Mike takes over and confirms in Hermes.
- Destructive Obsidian operations and writes outside `Agent` are handed off; ordinary note reads and scoped `Agent` note creates/updates work by voice.
- The dedicated session is visible and continuable in the installed Hermes Desktop; pending approval behavior is tested, not assumed.
- Unsupported requests, API outages, timeouts, and failed handoffs produce truthful spoken responses and never claim completion.
- Adding a capability backed by an already registered tool requires policy/config registration but no bridge-specific feature branch.
- Unregistered tools/capabilities are denied by default; test prompt injection, repeated delivery, oversized history, and duplicate handoff/write attempts.
- The existing uncommitted bridge and README changes are preserved.

## Implementation boundary

Expected bridge changes: capability/policy loading, request routing, persistent-session handoff, structured outcomes converted into speech-friendly replies, and safety/time/idempotency handling. The HA custom integration should remain unchanged if its existing `reply` contract is sufficient; change it only if verified API behavior requires an explicit handoff/result field. Hermes API server configuration and an app-side approval surface may be needed after compatibility testing. Do not implement Invoice Ninja writes as part of the first voice-path milestone.
