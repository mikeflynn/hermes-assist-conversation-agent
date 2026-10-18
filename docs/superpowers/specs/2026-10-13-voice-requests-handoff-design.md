# Voice Requests Handoff — Design

**Status:** Historical proposal. The approved routing contract is now documented in `docs/voice-requests-setup.md`; the future service ideas below are not part of the current voice scope.

## Goal

Keep ordinary questions, research requests, and clear simple Home Assistant commands on the synchronous voice path so Assist can speak their answers immediately. Use the persistent Hermes **Voice Requests** session only for work that needs confirmation or when Mike explicitly asks for that destination; answer length by itself is not a handoff reason.

## User-approved constraints

- The HA custom conversation integration forwards Assist requests to the bridge; the bridge handles cached briefs and uses the synchronous Hermes API for ordinary questions and clear simple device commands.
- Existing calendar and Things cache-backed behavior remains intact.
- Requests needing confirmation, and requests explicitly directed there by Mike, appear in a dedicated **Voice Requests** session in the Hermes app.
- Direct tool access is limited to the exact Home Assistant and Conduit tools enabled in `bridge/voice_capabilities.json`. The registry grants access but does not itself provide per-call approval; confirmation-sensitive requests are routed to the session before the inline model call whenever the bridge classifier recognizes them.
- Future capabilities should be registered through a generic policy/capability mechanism rather than hard-coded into the bridge.
- Spoken replies should clearly distinguish completed answers, unsupported requests, and work that needs the Hermes session or user approval.

## Current state

At the time of the original inspection, the HA custom conversation integration forwarded text to `bridge.py` at `/api/chat`, and the routing always handed requests to Voice Requests. The approved implementation changes that behavior: the bridge now answers ordinary turns synchronously through `/v1/chat/completions` and uses `/v1/runs` only for handoff. The live API server/profile and exact tool inventory must still be verified before use.

## Proposed architecture

### Request flow

1. Calendar, Things, and news brief requests keep their cache-backed read-only behavior.
2. Other ordinary questions, research requests, and clear simple device commands run synchronously through `/v1/chat/completions`; the returned text is sent directly to Assist. Answer length alone never triggers a handoff.
3. The bridge routes explicit Voice Requests destinations, explicit confirmation requests, and known confirmation-sensitive action classes to the persistent session. The inline model is also instructed to return a transport-only `HANDOFF_REQUIRED:` marker before acting when confirmation is required.
4. Direct API access requires an exact match between the authenticated enabled-tool inventory and `bridge/voice_capabilities.json`; no unregistered tools are available to voice.
5. The bridge returns one of a small explicit set of outcomes:
   - **Answered:** a cached brief or synchronous voice turn produced a response for Assist.
   - **Handed off:** the request is represented in the dedicated Voice Requests Hermes session and needs attention there.
   - **Unsupported:** no registered capability can handle it; the spoken response says so plainly and may offer the Hermes session as the next step.
   - **Unavailable/error:** the handoff or capability failed; the response must not imply success.
6. Only handoffs use the persistent Voice Requests session; synchronous API turns do not target that pinned session, though Hermes may retain them according to its normal API chat-session behavior.
7. Do not describe the registry or prompt as a universal approval sandbox: the bridge classifier and model instruction handle confirmation routing, while the registered direct tools themselves remain callable on an explicit clear request.

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

### Current capability scope

- Existing calendar/Things/news briefs: preserve their read-only cache-backed behavior.
- Home Assistant and Conduit: only the eight currently approved tools in `bridge/voice_capabilities.json` are exposed; clear simple requests are handled on the synchronous path.
- Additional services (including web search, Obsidian, or Invoice Ninja) are future proposals only. They require separate explicit policy approval, implementation, and verification before being enabled for voice.

## Voice response behavior

Responses must be concise and speech-friendly, and state what happens next. Examples (wording may vary):

- Read-only success: “The lights in the boy’s room are on.”
- Clear simple device action: “Done. The hallway lights are off.”
- Explicit handoff/confirmation: “I sent that to your Voice Requests session.”
- Unsupported: “I can’t do that from the voice assistant. I haven’t taken action.”
- Handoff failed: “I couldn’t send that to Hermes, so nothing was started.”

Only say a request was handed off after the session write is confirmed. Never describe a proposed operation as completed. Long answers and research requests remain inline; only explicit session requests and confirmation-sensitive work are handed off.

## Security and operational requirements

- Voice-originated tools are allowlisted; no inherited full CLI defaults. Exclude terminal, arbitrary code execution, and broad filesystem writes. The currently approved voice API inventory is limited to the exact Home Assistant and Conduit tools registered in `bridge/voice_capabilities.json`; additions require explicit policy authorization and a matching live-inventory check.
- Do not enable future integrations such as Obsidian or Invoice Ninja for voice until they have their own explicitly reviewed policy entries and implementation.
- Keep API keys out of prompts, logs, and speech. Authenticate bridge-to-Hermes API calls; bind services to trusted interfaces and use TLS/access controls when traffic crosses an untrusted network.
- Preserve request IDs and use idempotency/deduplication for handoffs and later writes to prevent retries from creating duplicate records.
- Bound request length, history, concurrency, and runtime. Ensure truncation cannot remove the user's current request while retaining stale history.
- Keep an audit trail of handoff ID, session ID, capability, proposal, approval outcome, and resulting record ID without logging credentials or unnecessary transcript content.

## Alternatives considered

1. **Generic registry plus persistent session and approval flow (recommended):** supports future services and a consistent user experience, with more initial integration work and a required verification of Desktop/API approval behavior.
2. **Feature-specific routing in `bridge.py`:** quicker initially but makes every new capability a bridge code change and encourages policy drift; rejected.
3. **Only emit a notification/request summary:** safer and simpler but does not provide the requested persistent, actionable Hermes thread; fallback only if session/approval integration proves unavailable.

## Verification and acceptance criteria

- Cached calendar, Things, and news responses remain available.
- A read-only Home Assistant state question returns its spoken answer synchronously without submitting a Voice Requests run.
- A clear simple Home Assistant command returns its spoken result synchronously without submitting a Voice Requests run.
- Research requests remain inline even when their response is longer than a quick fact.
- Explicit Voice Requests destinations and confirmation-sensitive tasks are handed off; the transport marker is never spoken.
- Inline answers and handoffs both require the live enabled-tool inventory to exactly match the registry.
- Unsupported requests, API outages, timeouts, and failed handoffs produce truthful spoken responses and never claim completion.
- Unregistered tools are denied by default; request history is bounded and the current utterance is not duplicated in the inline message history.

## Implementation boundary

Expected bridge changes: capability/policy loading, synchronous answer routing, explicit/confirmation-sensitive persistent-session handoff, structured outcomes converted into speech-friendly replies, and timeout/idempotency handling. The HA custom integration should remain unchanged while its existing `reply` contract is sufficient. Hermes API server configuration and Desktop approval behavior must be verified separately. The broader service ideas in this historical proposal are not included in the current approved scope.
