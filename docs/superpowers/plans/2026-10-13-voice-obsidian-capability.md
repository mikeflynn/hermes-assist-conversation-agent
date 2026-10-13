# Voice Web and Obsidian Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add web lookup and scoped Obsidian voice access: read/write in `Agent`, read-only elsewhere in the vault.

**Architecture:** Extend the core voice capability registry with web search and a dedicated path-scoped Obsidian adapter. Do not grant the voice agent general filesystem write tools; enforce Obsidian path and operation constraints in the adapter itself.

**Tech Stack:** Python 3.9-compatible tools, Hermes web capability, stdlib path handling, Hermes-supported MCP/tool integration.

**Spec:** `docs/superpowers/specs/2026-10-13-voice-requests-handoff-design.md`

## Global Constraints

- Depends on the completed core handoff plan: `docs/superpowers/plans/2026-10-13-voice-request-core.md`.
- Voice may create/update notes only under the vault's `Agent` directory; reads are allowed throughout the vault.
- Delete and bulk destructive operations remain approval-gated; unregistered capabilities are denied.
- Do not expose terminal, code execution, general filesystem writes, or HA control to the voice API platform.
- A spoken success is returned only after the relevant read/write operation is verified.

## Review Focus

- Path traversal (`../`, absolute paths, encoded separators) cannot escape the vault — test in Task 1.
- Symlinks inside `Agent` cannot redirect writes outside the authorized folder — test in Task 1.
- Case/Unicode/path normalization cannot bypass the Agent boundary — test in Task 1.
- Missing or iCloud-offline files produce clear errors without false claims — test in Task 2.
- Prompt injection inside note contents cannot grant tools or broaden write scope — test in Task 3.

---

### Task 1: Path-scoped Obsidian access rules

**Files:**
- Create: `bridge/obsidian_access.py`
- Test: `tests/test_obsidian_access.py`

**Interfaces:**
- `ObsidianAccess(vault_root, agent_root)` exposes `resolve_read_path(note_path) -> Path` and `resolve_write_path(note_path) -> Path`.
- All paths are resolved beneath `vault_root`; writes additionally resolve beneath `agent_root`.
- Writes support only create/update/append of Markdown notes; deletion and bulk operations raise `PermissionError`.

- [ ] **Step 1: Write failing tests** for valid Agent reads/writes, read-only access outside Agent, traversal, absolute paths, symlink escape, missing file, directory writes, non-Markdown writes, delete, and bulk operation denial.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_obsidian_access.py' -v`** and confirm the missing adapter failures.
- [ ] **Step 3: Implement `ObsidianAccess`** with canonical path resolution and explicit operation checks; do not use the unrestricted Hermes file tool for voice writes.
- [ ] **Step 4: Re-run tests** and verify writes through symlink/path normalization attempts are denied.
- [ ] **Step 5: Commit** as `feat: enforce voice Obsidian path scope`.

### Task 2: Obsidian read/search/write tools

**Files:**
- Create: `bridge/obsidian_tools.py`
- Modify: `bridge/voice_capabilities.json`
- Test: `tests/test_obsidian_tools.py`

**Interfaces:**
- `search_notes(query, limit=5) -> list[NoteMatch]` searches Markdown notes anywhere in the vault and returns bounded snippets/paths.
- `read_note(note_path) -> NoteContent` reads any Markdown note under the vault.
- `create_agent_note(note_path, content) -> NoteWriteResult`, `update_agent_note(note_path, content) -> NoteWriteResult`, and `append_agent_note(note_path, content) -> NoteWriteResult` accept only paths under `Agent`.
- The tool adapter uses `ObsidianAccess` for every filesystem operation and returns no content outside the requested scope.

- [ ] **Step 1: Write failing tests** for text/filename search, note read, create/update/append in Agent, rejection of write outside Agent, and post-write read-back verification.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_obsidian_tools.py' -v`** and verify the expected failures.
- [ ] **Step 3: Implement the narrow tool functions** and register them as a dedicated voice capability with the policy from the core plan.
- [ ] **Step 4: Re-run tests** with temporary vault fixtures and verify changed bytes/content exactly match expectations.
- [ ] **Step 5: Commit** as `feat: add scoped Obsidian voice tools`.

### Task 3: Web lookup and end-to-end voice behavior

**Files:**
- Modify: `bridge/voice_capabilities.json`
- Modify: `docs/voice-requests-setup.md`
- Test: `tests/test_voice_capability_routing.py`

**Interfaces:**
- The `web_search` capability is read-only and maps only to the installed Hermes web search toolset.
- Voice routing only exposes registered capabilities; there is no fallback to terminal/browser automation for general queries.

- [ ] **Step 1: Write failing tests** for web lookup registration, unsupported/unregistered tools, Obsidian Agent writes vs outside-vault writes, and spoken result/error phrases.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_voice_capability_routing.py' -v`** and verify the policy tests fail as expected.
- [ ] **Step 3: Register web search and Obsidian tools** in the voice capability config, keeping browser automation and unrelated tools disabled.
- [ ] **Step 4: Run all tests** and perform one live web lookup plus one read, one Agent note write, and one rejected outside-Agent write through the voice path.
- [ ] **Step 5: Commit** as `feat: enable web and scoped Obsidian voice access`.
