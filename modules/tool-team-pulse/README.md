# amplifier-module-tool-team-pulse

Amplifier tool module wrapping the **team-pulse lens API** — mounted as **three
tools**: every read behind one `op` enum, every write behind another, and
online generation left deliberately on its own.

## Exposed tools

### `team_pulse_read(op=…)` — all reads

| op | Endpoint | Purpose |
|---|---|---|
| `info` | `GET /api/lens/info` | Self-doc — the **live** resource types + collections. Read this first; don't hardcode the surface. |
| `resources` | `GET /api/lens/resources` | List resources; `type` filter (hidden types return 400), `collection`, and `status` (question lifecycle) params |
| `search` | `GET /api/lens/resources/search` | Text search; a bare query searches the corpus; pass `collection` to scope |
| `prefix` | `GET /api/lens/resources/prefix/{prefix}` | Hierarchical ID listing |
| `get` | `GET /api/lens/resources/{id}` | Fetch one resource |
| `graph` | `GET /api/lens/graph` | Raw structural entity graph. Large payload; may include frozen/aging data — not a current-state source; use sparingly. |
| `whoami` | `GET /api/lens/whoami` | The **server-verified** caller identity (handle/member_id) |
| `status` | — (local) | THIS client's resolved config: `base_url`, `auth_mode`, no network call and no secrets. Works even when auth is broken. |

### `team_pulse_write(op=…)` — writes and local setup

| op | Endpoint | Purpose |
|---|---|---|
| `submit_answer` | `POST /api/lens/answers` | Record a session-mined answer to a reflection question. `question_id` is the **bare slug**, never `questions/<slug>`. |
| `download_corpus` | `GET /api/lens/corpus.zip` | Bulk-download the mined corpus to a local dir; returns a summary, never page bodies. Requires per-user az bearer auth — a shared API key is refused (403). |
| `configure` | — (local) | Persist this user's endpoint URL to `~/.amplifier/team-pulse/config.yaml`; effective immediately, no restart. |

### `team_pulse_ask` — unchanged, and deliberately separate

| Tool | Endpoint | Purpose |
|---|---|---|
| `team_pulse_ask` | `POST /api/lens/ask` | Ask Team Pulse; returns a corpus-grounded generated answer (markdown, cites `tp://doc/…` sources). `prompt` required, `focus` optional. |

`ask` triggers **server-side LLM spend**, so it is not folded behind an `op`
enum: it stays an explicit, undisguised call. Prefer `team_pulse_read` and
compose the answer yourself; call `ask` only when the user explicitly directs
Team Pulse to answer.

## Old name → new call

The twelve formerly-separate tools map one-to-one onto the three above. The same
table lives in code as `COMPAT_TABLE` (importable from the package).

| Old tool | New call |
|---|---|
| `team_pulse_get` | `team_pulse_read(op="get", id=…)` |
| `team_pulse_search` | `team_pulse_read(op="search", q=…)` |
| `team_pulse_prefix` | `team_pulse_read(op="prefix", prefix=…)` |
| `team_pulse_resources` | `team_pulse_read(op="resources", type=…)` |
| `team_pulse_graph` | `team_pulse_read(op="graph")` |
| `team_pulse_info` | `team_pulse_read(op="info")` |
| `team_pulse_whoami` | `team_pulse_read(op="whoami")` |
| `team_pulse_status` | `team_pulse_read(op="status")` |
| `team_pulse_submit_answer` | `team_pulse_write(op="submit_answer", …)` |
| `team_pulse_download_corpus` | `team_pulse_write(op="download_corpus", dest_dir=…)` |
| `team_pulse_configure` | `team_pulse_write(op="configure", url=…)` |
| `team_pulse_ask` | `team_pulse_ask(prompt=…)` — unchanged |

Parameter names and semantics are otherwise identical to before; `op` is the
only new key.

## Configuration

```yaml
tools:
  - module: tool-team-pulse
    source: ...
    config:
      url: "https://<your-team-pulse-endpoint>"
      key: "tp_..."   # mint at <url>/admin
```

The bundle ships no default endpoint. A missing URL is not a mount-time error —
it surfaces as a `not_configured` envelope on the first call that needs the
network, pointing the agent at `team_pulse_write(op="configure", url=…)`.

## Error handling

Errors from the lens API are passed through verbatim — the original error
envelope `{error: {code, message, status}}` is preserved in `ToolResult.error`.
Network or transport failures produce a synthetic `{code: "transport_error",
message, status: 0}` envelope.

## Development

```bash
uv sync --extra dev
uv run pytest
```
