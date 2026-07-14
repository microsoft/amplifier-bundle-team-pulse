# team-pulse-lib Examples

End-to-end example scripts that run against a **real HTTP server** — either the
built-in stdlib-only fake server or a live Team Pulse instance.  No mocking
inside the scripts; the fake server is a genuine TCP listener on an ephemeral
`127.0.0.1` port.

---

## Scripts

| Script | What it shows |
|--------|---------------|
| `azure_auth.py` | The four `TeamPulseClient` construction forms (`connect(base_url=...)`, `connect()`/`from_env()`, api-key, advanced explicit override) and each one's resolved provenance via `describe()` — **construction only, no `az login`, no network** |
| `fetch_questions.py` | Active question list, single-question lookup, `describe()` snapshot (no secrets, no network call) |
| `submit_answer.py` | Bare submit (empty metadata), metadata submit with session provenance inside `metadata` (schema v1 — both succeed against same server) |
| `answer_generator.py` | Full headless loop: discover active questions → synthesise an answer per question → submit bare / Phase-0 safe |
| `fake_team_pulse_server.py` | Shared stdlib-only fake server used by all three scripts and the test suite |

---

## Running (self-contained — no real server required)

Each script automatically spins up the built-in fake server when
`AMPLIFIER_TEAM_PULSE_URL` is not set.  Run from the `team-pulse-lib/`
directory so the `.venv` is picked up by `uv`:

```bash
cd amplifier-bundle-team-pulse/team-pulse-lib

uv run python examples/fetch_questions.py
uv run python examples/submit_answer.py
uv run python examples/answer_generator.py
```

---

## Pointing at a real server

```bash
export AMPLIFIER_TEAM_PULSE_URL=https://your-team-pulse-server.example.com
export AMPLIFIER_TEAM_PULSE_KEY=tp_your_api_key_here

uv run python examples/fetch_questions.py
uv run python examples/answer_generator.py
```

> `submit_answer.py` demonstrates two capability postures (supporting and
> non-supporting) simultaneously and always starts its own pair of fake
> servers.  For a real-server smoke-test of the write path, use
> `answer_generator.py` instead.

---

## Environment variables

| Variable | Effect |
|----------|--------|
| `AMPLIFIER_TEAM_PULSE_URL` | Override the server URL (skips fake-server spin-up) |
| `AMPLIFIER_TEAM_PULSE_KEY` | Override the API key (must start with `tp_`) |

---

## Schema v1 contract notes

**`metadata` carries session provenance (schema v1).**

- `metadata` on `AnswerUpload` is an opaque bag stored **verbatim** by the
  server.  Session provenance (`source_session_ids`) and any other context
  live **inside** `metadata`.
- **Bare submits** (empty `metadata`) always work and require no `user_id`.
- **Metadata submits** pass any opaque context inside `metadata` — the server
  persists it verbatim.  No capability guardrail required; the schema-v1
  server handles both forms.
- `submit_answer.py` demonstrates both paths side-by-side with explanatory
  output.

Deploy-server-first sequencing ensures the client is never ahead of the
server when sending `metadata`.
