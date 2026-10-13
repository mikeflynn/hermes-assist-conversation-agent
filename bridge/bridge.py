#!/usr/bin/env python3
"""Small HTTP bridge from Home Assistant Assist to Hermes Agent.

Endpoints:
- GET /health
- POST /api/chat with an Authorization header containing the bridge API key

This bridge is optional. HACS installs only the Home Assistant custom
integration; run this bridge separately on the machine that has Hermes Agent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import hashlib
import ipaddress
import shutil
import urllib.parse
from collections import OrderedDict

from .voice_responses import VoiceOutcome, format_spoken_reply
from .voice_policy import VoicePolicy

_HANDOFF_CACHE: OrderedDict[str, tuple[float, VoiceOutcome]] = OrderedDict()
HANDOFF_CACHE_TTL = 300
HANDOFF_CACHE_MAX = 512
VOICE_POLICY = VoicePolicy(())
_HANDOFF_LOCK = threading.Lock()
MAX_REQUEST_CHARS = 6000
MAX_CONTEXT_CHARS = 12000
MAX_CONCURRENT_HANDOFFS = threading.BoundedSemaphore(4)

HOST = os.environ.get("HERMES_ASSIST_HOST", "127.0.0.1")
PORT = int(os.environ.get("HERMES_ASSIST_PORT", "8765"))
KEY_FILE = Path(os.environ.get("HERMES_ASSIST_KEY_FILE", "./hermes-assist-bridge.key"))
HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")
HERMES_REPO = os.environ.get("HERMES_REPO", "")
HERMES_ENV_FILE = os.environ.get("HERMES_ENV_FILE", "")
TIMEOUT = int(os.environ.get("HERMES_ASSIST_TIMEOUT", "120"))
MAX_PROMPT_CHARS = int(os.environ.get("HERMES_ASSIST_MAX_PROMPT_CHARS", "6000"))
MAX_HISTORY_MESSAGES = int(os.environ.get("HERMES_ASSIST_MAX_HISTORY_MESSAGES", "8"))
USE_DIRECT_AGENT = os.environ.get("HERMES_ASSIST_USE_DIRECT_AGENT", "0").lower() in {"1", "true", "yes"}
MODEL = os.environ.get("HERMES_ASSIST_MODEL", "")
PROVIDER = os.environ.get("HERMES_ASSIST_PROVIDER", "")
TOOLSETS = [x.strip() for x in os.environ.get("HERMES_ASSIST_TOOLSETS", "").split(",") if x.strip()]
MAX_TURNS = int(os.environ.get("HERMES_ASSIST_MAX_TURNS", "8"))
REASONING_EFFORT = os.environ.get("HERMES_ASSIST_REASONING", "minimal")
CALENDAR_BRIEF_PATH = os.environ.get(
    "HERMES_ASSIST_CALENDAR_BRIEF",
    str(Path.home() / ".hermes" / "calendar_briefs" / "current.md"),
)
THINGS_BRIEF_PATH = os.environ.get(
    "HERMES_ASSIST_THINGS_BRIEF",
    str(Path.home() / ".hermes" / "things_briefs" / "current.md"),
)
NEWS_BRIEF_PATH = os.environ.get(
    "HERMES_ASSIST_NEWS_BRIEF",
    str(Path.home() / ".hermes" / "news_briefs" / "current.md"),
)

SYSTEM_PROMPT = f"""You are Hermes Agent answering through Home Assistant Assist.
Keep replies concise and speech-friendly. Avoid Markdown tables and visual-only instructions.
Use the recent conversation context to resolve pronouns and follow-up questions.
Safety: do not unlock doors, disable alarms, delete/send email, or make broad smart-home changes unless the spoken request is explicit and unambiguous. If unsure, ask a short clarifying question.
For ordinary device-control phrases that Home Assistant should handle directly, say briefly that this command should be routed to Home Assistant's built-in agent unless you can safely complete it with your available tools.

Calendar handling:
- For requests about today's schedule, tomorrow's schedule, or upcoming calendar events, read the pre-generated calendar brief at {CALENDAR_BRIEF_PATH} using the file-reading tool.
- Do not fetch calendar URLs, parse ICS feeds, or use execute_code for schedule requests; the morning calendar job already performs that work.
- Treat the date and timezone in the brief as authoritative. If the brief is missing or clearly stale, say that the calendar brief is unavailable rather than attempting a live refresh.

Things handling:
- For requests about tasks, to-dos, or what needs to be done today, read the pre-generated Things Today brief at {THINGS_BRIEF_PATH} using the file-reading tool.
- Do not query Things3 live, modify tasks, or use execute_code for task-list requests; the Things cron already performs the read-only refresh.
- The Things brief is intentionally prioritized and bounded, not a complete task list. Say so if the user asks for every task or if the file is missing or stale.

News handling:
- For requests for today's news, daily news, cybersecurity news, AI news, Apple/security updates, or the morning brief, read the pre-generated news brief at {NEWS_BRIEF_PATH} using the file-reading tool.
- Do not browse live news, fetch RSS feeds, or use execute_code for news requests; the morning news job already performs that read-only refresh.
- Treat the brief's 24-hour window, source failures, and freshness metadata as authoritative. If missing or stale, say the news brief is unavailable rather than attempting a live refresh.
"""

_AGENT = None
_AGENT_LOCK = threading.Lock()
_AGENT_READY = False
_AGENT_ERROR: str | None = None


def load_env_file(path: str) -> None:
    """Load simple KEY=VALUE secrets into the bridge process environment."""
    if not path:
        return
    env_path = Path(path).expanduser()
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


load_env_file(HERMES_ENV_FILE)


def load_key() -> str:
    try:
        return KEY_FILE.expanduser().read_text().strip()
    except FileNotFoundError:
        return os.environ.get("HERMES_ASSIST_API_KEY", "").strip()


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _content_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                txt = part.get("text") or part.get("content")
                if isinstance(txt, str):
                    parts.append(txt)
        return " ".join(parts).strip()
    return ""


def format_history(data: dict[str, Any], current_text: str) -> str:
    """Extract concise previous chat context from Home Assistant's Assist chat log."""
    chat_log = data.get("chat_log")
    if not isinstance(chat_log, dict):
        return ""
    items = chat_log.get("content")
    if not isinstance(items, list):
        return ""

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        text = _content_text(item)
        if not text:
            continue
        if role == "user" and text.strip().lower() == current_text.strip().lower():
            continue
        speaker = "User" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {text[:600]}")

    if not lines:
        return ""
    return "Recent conversation, oldest to newest:\n" + "\n".join(lines[-MAX_HISTORY_MESSAGES:]) + "\n"


def build_voice_context(current_text: str, history: str) -> str:
    return (history or "")[-MAX_CONTEXT_CHARS:] + "\nUser said: " + current_text[:MAX_REQUEST_CHARS]


def handoff_request(client, state_path: str, request_id: str, text: str, context: str) -> VoiceOutcome:
    if not request_id or len(text) > MAX_REQUEST_CHARS:
        return VoiceOutcome("unsupported", "I can't do that from the voice assistant. I haven't taken action.", request_id)
    key = hashlib.sha256(json.dumps([str(Path(state_path).expanduser().resolve()), request_id, text, context], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    with _HANDOFF_LOCK:
        now = time.monotonic()
        for old_key, (created, _) in list(_HANDOFF_CACHE.items()):
            if now - created > HANDOFF_CACHE_TTL:
                del _HANDOFF_CACHE[old_key]
        cached = _HANDOFF_CACHE.get(key)
        if cached is not None:
            _HANDOFF_CACHE.move_to_end(key)
            return cached[1]
        if not MAX_CONCURRENT_HANDOFFS.acquire(False):
            return VoiceOutcome("unavailable", "I couldn't send that to Hermes, so nothing was started.", request_id)
        try:
            session_id = client.get_or_create_voice_session(state_path)
            bounded_context = (context or "")[-MAX_CONTEXT_CHARS:]
            if text not in bounded_context:
                bounded_context = (bounded_context + "\nUser said: " + text[:MAX_REQUEST_CHARS])[-MAX_CONTEXT_CHARS:]
            result = client.submit_voice_request(session_id, request_id, text, {"source": "voice", "history": bounded_context})
            if getattr(result, "status", None) != "accepted" or getattr(result, "session_id", None) != session_id:
                return VoiceOutcome("unavailable", "I couldn't send that to Hermes, so nothing was started.", request_id)
            outcome = VoiceOutcome("handed_off", "I sent that to your Voice Requests session.", request_id, session_id)
            _HANDOFF_CACHE[key] = (now, outcome)
            _HANDOFF_CACHE.move_to_end(key)
            while len(_HANDOFF_CACHE) > HANDOFF_CACHE_MAX:
                _HANDOFF_CACHE.popitem(last=False)
            return outcome
        except Exception:
            return VoiceOutcome("unavailable", "I couldn't send that to Hermes, so nothing was started.", request_id)
        finally:
            MAX_CONCURRENT_HANDOFFS.release()


def get_voice_client():
    base_url = os.environ.get("HERMES_API_URL", "").strip()
    api_key = os.environ.get("HERMES_API_KEY", "").strip()
    if not base_url or not api_key:
        return None
    try:
        parsed = urllib.parse.urlsplit(base_url)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or "?" in base_url or "#" in base_url:
            return None
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host.lower() == "localhost"
        configured_toolsets = _configured_api_toolsets()
        if not loopback or configured_toolsets != ["no_mcp"]:
            return None
        timeout = int(os.environ.get("HERMES_API_TIMEOUT_SECONDS", "10"))
        if not 1 <= timeout <= 30:
            return None
        if os.environ.get("HERMES_ASSIST_TOOLSETS", "").strip():
            return None
        policy = get_voice_policy()
        from .hermes_api import HermesApiClient
        client = HermesApiClient(base_url, api_key, timeout=timeout)
        client.voice_policy = policy
        return client
    except Exception:
        return None


def _configured_api_toolsets():
    """Read the active Hermes profile's API toolsets without changing config."""
    executable = shutil.which("hermes")
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "config", "get", "--json", "platform_toolsets.api_server"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=False,
        )
        if result.returncode != 0:
            return None
        value = json.loads(result.stdout)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return None
        return value
    except Exception:
        return None


def voice_state_path() -> str:
    configured = os.environ.get("HERMES_VOICE_STATE_PATH")
    if configured:
        return str(Path(configured).expanduser())
    home = os.environ.get("HERMES_HOME")
    root = Path(home).expanduser() if home else Path.home() / ".hermes"
    return str(root / "voice_requests_state.json")


def voice_policy_path() -> str:
    return os.environ.get("HERMES_VOICE_POLICY_FILE", "")


def get_voice_policy() -> VoicePolicy:
    path = voice_policy_path()
    return VoicePolicy.from_file(path) if path else VoicePolicy(())


def derive_request_id(conversation_id: str, text: str, history: str) -> str:
    canonical = json.dumps([conversation_id or "", (history or "")[-MAX_CONTEXT_CHARS:], text[:MAX_REQUEST_CHARS]], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cached_brief(text: str, calendar_path: str, things_path: str, news_path: str) -> VoiceOutcome | None:
    lowered = text.lower()
    if any(word in lowered for word in ("calendar", "schedule", "event")):
        path = calendar_path
    elif any(word in lowered for word in ("task", "todo", "to-do", "things", "need to do")):
        path = things_path
    elif any(word in lowered for word in ("news", "cybersecurity", "apple updates", "morning brief")):
        path = news_path
    else:
        return None
    try:
        content = Path(path).expanduser().read_text(encoding="utf-8")[:4000]
    except (OSError, ValueError):
        content = ""
    if not content.strip():
        content = "That cached brief is unavailable."
    return VoiceOutcome("answered", content.strip())


def route_voice_request(text: str, client, policy: VoicePolicy, calendar_path: str, things_path: str, request_id: str = "request", context: str = "", news_path: str = NEWS_BRIEF_PATH) -> VoiceOutcome:
    cached = _cached_brief(text, calendar_path, things_path, news_path)
    if cached is not None:
        return cached
    if policy.allowed_tools() and not policy.authorize("voice_handoff", "hermes_api", "read", None):
        return VoiceOutcome("unsupported", "I can't do that from the voice assistant. I haven't taken action.", request_id)
    if client is None:
        return VoiceOutcome("unavailable", "I couldn't send that to Hermes, so nothing was started.", request_id)
    try:
        client.get_capabilities()
        inventory = client.get_enabled_tool_inventory()
        if inventory != policy.allowed_tools():
            return VoiceOutcome("unavailable", "I couldn't send that to Hermes, so nothing was started.", request_id)
    except Exception:
        return VoiceOutcome("unavailable", "I couldn't send that to Hermes, so nothing was started.", request_id)
    return handoff_request(client, voice_state_path(), request_id, text, context)


def get_agent():
    """Create one in-process Hermes agent and reuse it across voice requests."""
    global _AGENT, _AGENT_READY, _AGENT_ERROR
    if _AGENT is not None:
        return _AGENT
    with _AGENT_LOCK:
        if _AGENT is not None:
            return _AGENT
        try:
            if HERMES_REPO:
                sys.path.insert(0, HERMES_REPO)
                os.chdir(HERMES_REPO)
            from hermes_constants import parse_reasoning_effort
            from run_agent import AIAgent

            kwargs: dict[str, Any] = {
                "enabled_toolsets": TOOLSETS or None,
                "max_iterations": MAX_TURNS,
                "quiet_mode": True,
                "skip_context_files": True,
                "skip_memory": True,
                "reasoning_config": parse_reasoning_effort(REASONING_EFFORT),
                "platform": "homeassistant",
            }
            if MODEL:
                kwargs["model"] = MODEL
            if PROVIDER:
                kwargs["provider"] = PROVIDER
            _AGENT = AIAgent(**kwargs)
            _AGENT_READY = True
            _AGENT_ERROR = None
            return _AGENT
        except Exception as exc:  # noqa: BLE001 - fallback to CLI path
            _AGENT_ERROR = str(exc)
            _AGENT_READY = False
            raise


def call_hermes_direct(prompt: str) -> tuple[bool, str]:
    """Call the in-process Hermes agent. Returns (ok, text)."""
    try:
        agent = get_agent()
        with _AGENT_LOCK:
            return True, (agent.chat(prompt) or "").strip()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def call_hermes_cli(prompt: str) -> tuple[bool, str]:
    """Fallback CLI call, slower but simple and robust."""
    cmd = [HERMES_BIN, "chat", "-q", prompt, "--source", "home-assistant-assist", "-Q", "--max-turns", str(MAX_TURNS)]
    if PROVIDER:
        cmd += ["--provider", PROVIDER]
    if MODEL:
        cmd += ["-m", MODEL]
    if TOOLSETS:
        cmd += ["--toolsets", ",".join(TOOLSETS)]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=TIMEOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "Hermes exited with an error")[-2000:]
    return True, (proc.stdout or "").strip()


class Handler(BaseHTTPRequestHandler):
    server_version = "HermesAssistBridge/1.2"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            json_response(self, 200, {"ok": True, "service": "hermes-assist-bridge", "time": time.time(), "direct_agent": USE_DIRECT_AGENT, "agent_ready": _AGENT_READY, "agent_error": _AGENT_ERROR, "model": MODEL, "provider": PROVIDER, "toolsets": TOOLSETS, "max_turns": MAX_TURNS, "reasoning": REASONING_EFFORT})
        else:
            json_response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/chat":
            json_response(self, 404, {"error": "not_found"})
            return

        expected = load_key()
        auth = self.headers.get("Authorization", "")
        if not expected or auth != f"Bearer {expected}":
            json_response(self, 401, {"error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(min(length, 1024 * 1024))
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as exc:
            json_response(self, 400, {"error": "bad_json", "detail": str(exc)})
            return

        text = str(data.get("text", "")).strip()
        if not text:
            json_response(self, 400, {"error": "missing_text"})
            return

        conversation_id = str(data.get("conversation_id") or "")
        language = str(data.get("language") or "")
        device_id = str(data.get("device_id") or "")
        extra_system_prompt = str(data.get("extra_system_prompt") or "")
        history = format_history(data, text)

        if len(text) > MAX_REQUEST_CHARS:
            outcome = VoiceOutcome("unsupported", "That request is too long for the voice assistant. I haven't taken action.")
            json_response(self, 200, {"reply": format_spoken_reply(outcome), "outcome": outcome.status, "conversation_id": conversation_id or None})
            return
        request_id = str(data.get("request_id") or derive_request_id(conversation_id, text, history))
        client = get_voice_client()
        policy = getattr(client, "voice_policy", VOICE_POLICY)
        outcome = route_voice_request(text, client, policy, CALENDAR_BRIEF_PATH, THINGS_BRIEF_PATH, request_id, format_history(data, text), NEWS_BRIEF_PATH)
        json_response(self, 200, {"reply": format_spoken_reply(outcome), "outcome": outcome.status, "request_id": outcome.request_id, "session_id": outcome.session_id, "conversation_id": conversation_id or None})
        return


def main() -> None:
    if USE_DIRECT_AGENT:
        try:
            get_agent()
        except Exception as exc:  # noqa: BLE001
            print(f"Direct Hermes agent unavailable, CLI fallback will be used: {exc}", file=sys.stderr, flush=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Hermes Assist Bridge listening on http://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
