# J.A.R.V.I.S. backend — Phase 1

For personal computer installation, follow [START-HERE.md](START-HERE.md).
The macOS launcher is **Start Jarvis.command**; it opens a setup window and
starts the browser interface without requiring a public website.

Python 3.12+ backend with a J.A.R.V.I.S.-style command center, served at `/`.
Enter the backend `JARVIS_API_TOKEN` using the settings button to connect.
The token stays in tab memory; only a conversation ID is saved in browser storage.
Provider credentials stay on the server. The interface supports streaming text,
stop, new conversations, history, confirmed deletion, and actual host telemetry.
Voice and other planned modules are displayed as unavailable.

## Install and run

```bash
cd /workspace/Alzagyzag
export UV_CACHE_DIR=/workspace/.cache/uv
uv sync --frozen --extra dev
cp .env.example .env  # only if .env does not already exist
# Edit .env securely, then:
.venv/bin/uvicorn jarvis.main:app --host 127.0.0.1 --port 8000
```

The server starts without keys; `/healthz` checks the database. Chat requires
`JARVIS_API_TOKEN` (a strong, independently generated application bearer token)
and `JARVIS_PROVIDER_API_KEY` for hosted providers. Enter credentials through
secure environment settings or an untracked local `.env`; never paste keys into
chat, URLs, logs, or source files. All authenticated clients share one owner and
can access all sessions: this foundation is for a single user, not multi-tenant use.

Configuration lives in `jarvis/config.py` and supports `JARVIS_` environment
variables. `JARVIS_PERSONALITY` overrides the default persona.
Hosted provider URLs require HTTPS; only loopback local services may use HTTP.
The model and endpoint must be supported by the selected provider.

Supported adapters: OpenAI, other OpenAI-compatible SSE endpoints (including
Groq), and an independently installed Ollama service via its `/v1` endpoint.
Set `JARVIS_PROVIDER=openai_compatible` and the provider's base URL/model/key for
compatible services; set `ollama` for local inference. Anthropic and Gemini
native adapters, automatic routing, and failover are not implemented.
The `Provider` protocol in `jarvis/providers.py` is the extension point; tests
inject an implementation without making external calls.

## HTTP API

OpenAPI is available at `/openapi.json`; interactive documentation at `/docs`.
Use `Authorization: Bearer <application-token>` on `/api/*` requests.

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Unauthenticated liveness and database readiness |
| `POST /api/chat` | Text response with a new or supplied UUID session |
| `GET /api/status` | Configuration and supported capabilities |
| `GET /api/diagnostics` | Database check and measured CPU/memory/disk values |
| `GET /api/sessions/{session_id}` | Persisted completed exchanges |
| `DELETE /api/sessions/{session_id}` | Delete a conversation |

Example chat body:

```json
{"message":"Good morning, Jarvis","session_id":"706e654e-1f6c-4f36-9a4b-f89c46e2f4fb"}
```

Omit `session_id` to create one. Reuse the returned ID to continue a conversation.
Only successfully completed exchanges are persisted. SQLite stores history in
`data/jarvis.sqlite3`; treat it as personal data. Recent context is bounded to
40 messages by default. History has no automatic retention policy yet; use the
delete endpoint. Back up SQLite with its supported backup tooling, not by
copying only the main file while WAL writes are active.

## WebSocket protocol

Connect to `/ws/assistant`, then authenticate within ten seconds:

```json
{"type":"auth","token":"<application-token>"}
```

After the `system.status` authenticated event, submit:

```json
{"type":"message.user","payload":{"message":"Hello"}}
```

Server events use this envelope:

```json
{"type":"message.delta","event_id":"<uuid>","timestamp":"<UTC ISO timestamp>","session_id":"<uuid>","correlation_id":"<uuid>","payload":{"text":"Hello"}}
```

Events: `assistant.thinking`, `message.delta`, `message.assistant`,
`assistant.idle`, `system.status`, `system.warning`, `system.error`.
`message.assistant` is the final text; deltas are incremental text, not separate
messages. Failed or cancelled streams do not commit partial exchanges. Send
`{"type":"cancel"}` to cancel the active response. One active response is allowed
per connection. A request's events carry the same correlation ID. Authentication
status events have null session/correlation IDs. Reconnect with your session ID;
event replay is not implemented.

## Validation

```bash
.venv/bin/python -m pytest -q
```

Tests use simulated providers and temporary databases. They exercise real API
requests, persistence across application instances, failure handling, missing
credentials, streaming, cancellation, validation, and rate limits. They do not
verify live paid APIs or voice hardware. A successful `/healthz` does not prove
model connectivity; authenticated chat must succeed to establish that.

## Scope and security

This is Phase 1, not the full system described in the master brief. Voice,
wake words, semantic memory, tools/computer control, scheduled tasks, research,
email/calendar, vision, smart home, routing, and proactive notifications remain
unimplemented; their endpoints are intentionally not simulated.

The assistant cannot execute commands or grant permissions. Provider requests
have timeouts and failures return safe error messages without provider bodies
or keys. Chat is limited to 60 requests/minute per process, four concurrent
generations, 16,000 input characters, and 100,000 response characters. Session
writes are serialized within one process. Run a single Uvicorn worker; distributed
limits, concurrent workers, and multi-user ownership need further work.

Bind to loopback for development. Production deployment needs TLS, ingress
controls, WebSocket frame/body size limits, connection limits, stronger identity
management, retention policies, and security review. No cross-origin permissions
are enabled; serve the supplied interface behind the same origin or explicitly
configure trusted origins in a later integration task. Diagnostics describe the
cloud machine, not the user's personal computer.

Next development phase: voice adapters and streaming audio, followed by memory
controls and permission-gated tools. Independently developed interfaces can also
use the documented API and WebSocket protocol.
