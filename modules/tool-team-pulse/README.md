# amplifier-module-tool-team-pulse

Amplifier tool module wrapping the **team-pulse lens API** — six read-only
GET wrappers, one write tool for session-mining answer submission, and one
online-generation tool.

## Exposed tools

| Tool | Endpoint | Purpose |
|---|---|---|
| `team_pulse_info` | `GET /api/lens/info` | Self-doc — the **live** resource types + collections. Read this first; don't hardcode the surface. |
| `team_pulse_resources` | `GET /api/lens/resources` | List resources; `type` filter (currently `member`/`question` — hidden types return 400) and `collection` param |
| `team_pulse_search` | `GET /api/lens/resources/search` | Text search; a bare query searches the corpus; pass `collection` to scope |
| `team_pulse_prefix` | `GET /api/lens/resources/prefix/{prefix}` | Hierarchical ID listing |
| `team_pulse_get` | `GET /api/lens/resources/{id}` | Fetch one resource |
| `team_pulse_graph` | `GET /api/lens/graph` | Raw structural entity graph. May include frozen/aging data — not a current-state source; use sparingly. |
| `team_pulse_submit_answer` | `POST /api/lens/answers` | Record a session-mined answer to a reflection question |
| `team_pulse_ask` | `POST /api/lens/ask` | Ask Team Pulse; returns a corpus-grounded generated answer (markdown, cites `tp://doc/…` sources). `prompt` required, `focus` optional. |

## Configuration

```yaml
tools:
  - module: tool-team-pulse
    source: ...
    config:
      url: "https://<your-team-pulse-endpoint>"
      key: "tp_..."   # mint at <url>/admin
```

Both `url` and `key` must be supplied — the bundle ships no default endpoint.
Mount fails fast if either remains empty after settings → env var resolution.

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
