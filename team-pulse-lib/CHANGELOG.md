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
- **azure-identity `DefaultAzureCredential` auth** — replaces the previous `az` CLI
  subprocess auth path; supports all standard Azure credential chains (managed identity,
  workload identity, VS Code, Azure CLI, environment variables) without shell invocation.
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
