# team-pulse-lib

Standalone async HTTP client for the [Team Pulse](https://github.com/microsoft-amplifier/amplifier-shared) API.

**Zero Amplifier dependency** — install and use this library in any Python project.

---

## Installation

### Via pip (git subdirectory)

```bash
pip install "team-pulse-lib @ git+https://github.com/microsoft-amplifier/amplifier-bundle-team-pulse.git#subdirectory=team-pulse-lib"
```

### Editable install (development)

```bash
cd team-pulse-lib
pip install -e ".[dev]"
```

---

## Phase 0 Status

This library is in **Phase 0** of a multi-phase rollout.

### What works today (Phase 0A — scaffold)

- Package installs and imports.
- `team_pulse_lib.__version__` is exported.

### Metadata is gesture-only (not persisted)

The `metadata` field on `AnswerUpload` is a **GESTURE-ONLY contract**.

The current Team Pulse server **silently drops** it — it is not persisted and will not appear in
subsequent reads.  Clients **MUST refuse the operation or emit a hard warning** rather than
silently pretending the metadata was stored.  This contract is present in the type signatures
to establish the shape for Phase 1.

Full round-trip metadata persistence ships in **Phase 1**.

---

## Breaking-Change Policy

This library follows [Semantic Versioning](https://semver.org/).

### Public API surface

The following shapes are part of the public API:

| Type | Notes |
|------|-------|
| `Question` | Question record returned by the server |
| `AnswerUpload` | Payload submitted to the answers endpoint |
| `SubmittedAnswer` | Answer confirmation returned by the server |
| `ClientInfo` | Optional caller-identity metadata bag (gesture-only in Phase 0) |

**Breaking change** = any change to a public shape or method signature that is not backward compatible.
Breaking changes **MUST** increment the **MAJOR** version.

### Pinning recommendations

Pin by version range or git tag in your dependency declaration:

```toml
# by version range
"team-pulse-lib>=0.1,<1.0"

# by git tag
"team-pulse-lib @ git+https://...#tag=0.1.0&subdirectory=team-pulse-lib"
```

---

## Versioning & breaking-change policy

`team-pulse-lib` follows [Semantic Versioning](https://semver.org/).

### What counts as public API

The **data/wire contract** — all field names, types, and shapes on `Question`,
`AnswerUpload`, `SubmittedAnswer`, and `ClientInfo` — is **public API** and is covered
by semver guarantees alongside the importable symbols and method signatures listed in
[CHANGELOG.md](CHANGELOG.md).

### What constitutes a breaking change

A **breaking change** (triggers a **MAJOR** version bump) is any backward-incompatible
modification to:

- A public class, exception, or function signature
- A data/wire field name or type
- The semantics of any exported method

Every breaking change **must** be recorded in `CHANGELOG.md` under a new versioned
section before the release is tagged.

### Pinning recommendations

Pin by version range or git tag to protect against unintended breakage:

```toml
# stable range (recommended)
"team-pulse-lib>=1,<2"

# exact git tag
"team-pulse-lib @ git+https://github.com/microsoft-amplifier/amplifier-bundle-team-pulse.git#tag=1.0.0&subdirectory=team-pulse-lib"
```

---

## CI

```bash
cd team-pulse-lib && python -m pytest -q
```

The test suite includes `tests/test_no_amplifier_imports.py`, which asserts zero Amplifier
ecosystem coupling at import time.  If that test fails, the offending `amplifier*` module(s)
will be named in the failure message — treat this as a real defect.

---

## Constructing a client (api-key vs Azure)

`TeamPulseClient.connect()` is the single recommended factory. It resolves the
URL, infers the auth strategy, defaults the Azure app id (audience), and stamps
the provenance — all in one call.

```python
from team_pulse_lib import TeamPulseClient

# RECOMMENDED — url in code, Azure inferred, app id defaulted.
# No key supplied -> Azure AzureCliCredential (your `az login` session). The
# audience defaults to the shipped DEFAULT_API_APP_ID (owned by the service).
# Set ONLY the URL.
client = TeamPulseClient.connect(base_url="https://my-deployment.example.com")

# ENV-DRIVEN (12-factor) — what a deployed/headless service uses.
# Reads AMPLIFIER_TEAM_PULSE_URL (and an optional tp_ key) from the environment.
client = TeamPulseClient.connect()        # equivalent: TeamPulseClient.from_env()

# API-KEY — a tp_-prefixed key flips inference to ApiKeyAuth.
client = TeamPulseClient.connect(base_url="https://my-deployment.example.com", key="tp_...")

async with client:                        # __aenter__ eagerly acquires the credential
    me = await client.whoami()
```

**Precedence (high → low):** explicit arg > env var
(`AMPLIFIER_TEAM_PULSE_URL` / `AMPLIFIER_TEAM_PULSE_KEY`) > config file
(`~/.amplifier/team-pulse/config.yaml`) > shipped default (api app id only).

**The rule on the Azure app id (audience):** it is a shipped `DEFAULT_API_APP_ID`
owned by the service. Consumers set **only the URL**. Override `api_app_id` **only**
when targeting a *different* deployment whose Entra audience is not the default —
via the advanced escape hatch:

```python
from team_pulse_lib import AzCredentialAuth, DEFAULT_API_APP_ID, TeamPulseClient

# ADVANCED — explicit override for a different deployment's audience.
client = TeamPulseClient(
    base_url="https://other-deployment.example.com",
    auth=AzCredentialAuth(api_app_id="<other-app-id>"),
)
```

`describe()` returns the resolved provenance (`auth_mode`, `credential_type`,
`api_app_id`, `base_url`, `resolved`) from **local state with no network call** —
you do not need to enter the context to inspect it. See
[`examples/azure_auth.py`](examples/azure_auth.py) for a runnable walkthrough of
all four forms (no `az login`, no network).

---

## API endpoint reference

Every call the client makes to the Team Pulse lens API. The two write/local rows are
the Phase-0 additions; the read methods were lifted from the prior client unchanged.

### Library methods (`TeamPulseClient`)

| Method | HTTP call |
|--------|-----------|
| `fetch_questions(status=...)` | `GET /api/lens/resources?type=question` (status filtered client-side) |
| `fetch_question(slug)` | `GET /api/lens/resources/questions/{slug}` |
| `upload_answer(answer)` | `POST /api/lens/answers` |
| `describe()` | *(local — no network; resolved client config)* |
| `info()` | `GET /api/lens/info` |
| `resources(type=, collection=)` | `GET /api/lens/resources` |
| `search(q, limit=50, collection=)` | `GET /api/lens/resources/search` |
| `prefix(prefix)` | `GET /api/lens/resources/prefix/{prefix}` |
| `get(resource_id)` | `GET /api/lens/resources/{id}` |
| `graph()` | `GET /api/lens/graph` |
| `whoami()` | `GET /api/lens/me` |
| `ask(prompt, focus=)` | `POST /api/lens/ask` |
| *capability probe* (guardrail) | `GET /api/lens/info` *(cached ~60s, advisory)* |

### Amplifier tools (thin shim → library method → endpoint)

| Tool | Library method | HTTP call |
|------|----------------|-----------|
| `team_pulse_info` | `info()` | `GET /api/lens/info` |
| `team_pulse_resources` | `resources()` | `GET /api/lens/resources` |
| `team_pulse_search` | `search()` | `GET /api/lens/resources/search` |
| `team_pulse_prefix` | `prefix()` | `GET /api/lens/resources/prefix/{prefix}` |
| `team_pulse_get` | `get()` | `GET /api/lens/resources/{id}` |
| `team_pulse_graph` | `graph()` | `GET /api/lens/graph` |
| `team_pulse_whoami` | `whoami()` | `GET /api/lens/me` |
| `team_pulse_ask` | `ask()` | `POST /api/lens/ask` |
| `team_pulse_submit_answer` | `upload_answer()` | `POST /api/lens/answers` |
| **`team_pulse_status`** *(new)* | `describe()` | *(local — no network, no secrets)* |
| `team_pulse_configure` | `save_config()` | *(local — writes `~/.amplifier/team-pulse/config.yaml`)* |

---

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 0A | **Done** | Scaffold — package installs, imports, version exported |
| 0B | Planned | HTTP client — `AsyncTeamPulseClient`, typed models, auth |
| 0C | Planned | Amplifier shim — thin wrapper that delegates to this library |
| 1   | Planned | Server-side: metadata persistence, full round-trip |
