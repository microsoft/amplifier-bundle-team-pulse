# Changelog

All notable changes to `team-pulse-lib` are documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/).

---

## Public API (covered by semver)

The following symbols and shapes form the **public API**.  Any backward-incompatible
change to them constitutes a **breaking change** and triggers a **MAJOR version bump**.

### Importable symbols

| Symbol | Kind | Notes |
|--------|------|-------|
| `TeamPulseClient` | class | Primary async client |
| `Question` | dataclass / TypedDict | Wire shape returned by the server |
| `AnswerUpload` | dataclass / TypedDict | Payload submitted to the answers endpoint |
| `SubmittedAnswer` | dataclass / TypedDict | Confirmation returned after upload |
| `ClientInfo` | dataclass / TypedDict | Provenance metadata returned by `describe()` |
| `TeamPulseError` | exception | Base exception class |
| `TeamPulseUnsupportedError` | exception | Raised when a server capability is absent |
| `TeamPulseAuthError` | exception | Raised on authentication failures |

### Data / wire shapes

All field names and types on `Question`, `AnswerUpload`, `SubmittedAnswer`, and
`ClientInfo` are **public API**.  Adding a new *optional* field is a **minor** change;
removing or renaming a field, or changing a field type, is a **breaking** (major) change.

### Public method signatures

```python
# Factory constructors
TeamPulseClient.from_env() -> TeamPulseClient
TeamPulseClient.from_config(path: str | Path) -> TeamPulseClient

# Core operations (requires async context manager)
async TeamPulseClient.fetch_questions() -> list[Question]
async TeamPulseClient.fetch_question(question_id: str) -> Question
async TeamPulseClient.upload_answer(payload: AnswerUpload) -> SubmittedAnswer
async TeamPulseClient.describe() -> ClientInfo
```

---

## [Unreleased]

### Added

- **Phase 0 initial library lift** — standalone `team-pulse-lib` package extracted from
  the Amplifier bundle into a zero-Amplifier-dependency Python library.  Installs via
  `pip install "team-pulse-lib @ git+https://...#subdirectory=team-pulse-lib"`.
- **azure-identity `AzureCliCredential` auth** — replaces the previous `az` CLI subprocess
  auth path with the SDK's own `AzureCliCredential` (same underlying mechanism: shells out
  to `az account get-access-token`, just without hand-rolled subprocess/parsing code).
  Deliberately narrower than `DefaultAzureCredential`: this tooling targets interactive
  user machines first, so the developer's `az login` session always wins — no silent
  fallback to an ambient managed identity, service-principal env var, or workload identity
  that happens to also be reachable on the host (the exact failure mode that motivated
  this choice: managed identity silently outranks `az login` on any IMDS-reachable host,
  e.g. an Azure VM). A caller that genuinely needs a different credential (managed
  identity, a service principal, VS Code sign-in, …) injects it explicitly via the
  `credential` parameter threaded through `AzCredentialAuth` and the `from_env` /
  `from_config` / `from_args` factories — not supported ambiently by design; revisit if a
  real headless/service use case surfaces.
- **Key / wins auth inference with force override** — `from_env()` and `from_config()`
  automatically select between API-key and Azure bearer-token auth based on available
  environment variables; callers can force either mode via an explicit parameter.
- **Capability guardrail raising `TeamPulseUnsupportedError`** — before performing
  operations that require a server feature, the client probes `/api/lens/info` and raises
  `TeamPulseUnsupportedError` with a human-readable message if the server does not
  advertise the required capability.
- **`describe() -> ClientInfo` — provenance metadata, never secrets** — returns a
  `ClientInfo` bag containing the base URL, auth mode in use, and library version; the
  method is explicitly designed never to include credentials, tokens, or key material.
