# Voice Requests bridge: secure setup

The Voice Requests handoff is optional and fails closed. The bridge constructs its API client only when credentials and a valid loopback URL are present, the active Hermes profile explicitly configures exactly the one-item list `["no_mcp"]` in `platform_toolsets.api_server`, and any supplied capability registry is readable and valid. Additional toolsets—including broad composites such as `hermes-api-server` or `terminal`—disable client construction. Before each run it also compares the authenticated concrete enabled-tool inventory with the registry's enabled tools. An empty/missing registry grants no optional tools; the API endpoint does not prove MCP is disabled.

## Prepare Hermes in the intended profile

Do this only after reviewing the current Hermes API-server documentation and confirming which profile the bridge service will run under. The API server must listen on loopback only, require authentication, and have the explicit `no_mcp` toolset sentinel in that same profile. Do not include broad or unreviewed tools. `/v1/toolsets` omits default MCP servers, which is why the bridge separately checks Hermes configuration.

Before enabling or starting the service, inspect the selected profile read-only:

```sh
hermes config get --json platform_toolsets.api_server
hermes config get gateway.api_server.enabled
```

The first command must return exactly the JSON list `["no_mcp"]`; an unset, malformed, or unreadable value, or any additional toolset, prevents client construction. The bridge uses the `hermes` executable found on its `PATH` and inherits the service environment/profile. Ensure those identify the intended Hermes installation and profile. Do not use `hermes config show` in shared logs because configuration output can contain sensitive values.

Only an authorized operator should apply Hermes API-server configuration or start it. Choose loopback binding and current supported auth settings from Hermes documentation; do not expose the API server to a LAN or the internet. Verify the profile/configuration first, then independently confirm the authenticated concrete API tool inventory is restricted. This repository task does not enable or start that server.

## Configure the bridge environment

Set these only in the bridge service's private environment or a secret manager; never commit them or print their values:

- `HERMES_API_URL`: `http://127.0.0.1:<port>` or `https://localhost:<port>`. HTTP/HTTPS is accepted only for `localhost` or a literal loopback IP. URL userinfo, query, and fragment are rejected.
- `HERMES_API_KEY`: the API-server credential. Use the server's supported credential workflow and keep the value private.
- `HERMES_API_TIMEOUT_SECONDS`: optional integer from `1` through `30`; defaults to `10`.
- `HERMES_HOME`: optional active Hermes home/profile root. The bridge's read-only config lookup runs through the `hermes` executable in the service's environment.
- `HERMES_VOICE_STATE_PATH`: optional persistent session state path. Defaults to `$HERMES_HOME/voice_requests_state.json`; if `HERMES_HOME` is unset, defaults to `~/.hermes/voice_requests_state.json`. Restrict file permissions to the bridge service account and back it up only as sensitive state.
- `HERMES_VOICE_POLICY_FILE`: optional JSON capability registry. If absent, the policy is empty and optional tools are denied. If supplied, it must be readable and valid; invalid or unreadable files disable client construction. `direct_tool_access` registers tools that the API server may execute on the model's behalf; it does not constrain arguments or require per-call approval. The `voice_handoff`/`hermes_api` transport marker is not part of the API-server tool inventory.

Do not set `HERMES_ASSIST_TOOLSETS` for this API handoff; a non-empty legacy local-agent selection is treated as unsafe and disables the API client. Do not place secrets in command-line arguments, shell history, source control, or diagnostic output.

## Voice routing behavior

- Cached calendar, Things, and news briefs keep their existing read-only path.
- Other ordinary questions, research requests, and clear simple device commands use `POST /v1/chat/completions` synchronously. The bridge returns the answer directly to Home Assistant Assist for speech; answer length alone does not trigger a handoff.
- The persistent **Voice Requests** session is used when the user explicitly directs a request/response there, asks for confirmation before an action, or requests an action the bridge classifies as confirmation-sensitive (for example destructive, financial, external-message, broad-setting, or resource-write work). Those requests use the asynchronous run/handoff path.
- The direct answer call is checked against the same authenticated enabled-tool inventory and the exact voice registry before it runs. Only registered tools are available to Hermes. The registry grants tool access but does not enforce per-call approval; the bridge's confirmation routing is a conservative classifier plus model instruction, not a general approval sandbox.
- Ordinary `/v1/chat/completions` turns do not target the pinned **Voice Requests** session. Hermes may record them according to its normal API chat-session behavior; this is separate from the dedicated handoff session.
- The handoff marker is transport-only and must never be spoken as the final answer. A handoff is reported only after the Voice Requests run is accepted.

## Verify without broadening access

1. Confirm the bridge service's `PATH`, active `HERMES_HOME`/profile, and private environment without displaying secrets.
2. Run the two read-only config lookups above in that same service environment. Confirm `platform_toolsets.api_server` is exactly `["no_mcp"]` (no additions) and the server is enabled only as intended.
3. Confirm the endpoint is loopback-only and authenticated. Use a read-only health/capability/inventory check; confirm the advertised `/v1/chat/completions`, `/v1/runs`, and session endpoints before testing. Do not invoke approval-gated tools.
4. Verify enabled API tool inventory exactly matches the optional registry before using direct voice tools or the handoff. Empty policy means no tools are permitted.
5. Test a read-only inline voice question and confirm its reply is returned directly without submitting to the pinned Voice Requests session. Test explicit handoff routing separately. Confirm session visibility/continuation and Desktop approval behavior before considering the capability-plan exit gate satisfied.

If there is no already-running safe API server, stop here. Do not enable/configure/start it or create credentials as part of this repository change. The live/Desktop compatibility gate remains pending explicit operator setup and authorization.
