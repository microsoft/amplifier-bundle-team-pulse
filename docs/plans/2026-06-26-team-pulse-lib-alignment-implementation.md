# Team Pulse Client/Lib Alignment Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Align `team-pulse-lib` and its Amplifier shim with the server's new schema-v1 answer contract: send the partner's flat wire body, move session provenance into `metadata`, and delete the entire capability-negotiation / guardrail subsystem.

**Architecture:** Two Python packages in one repo — the zero-dependency client library `team-pulse-lib/team_pulse_lib/` and the thin Amplifier tool shim `modules/tool-team-pulse/`. The library RAISES typed exceptions; the shim catches them and re-maps to tool envelopes. This plan strips out a now-obsolete subsystem (capability probe, guardrail, `TeamPulseUnsupportedError`, `server_supports_metadata`) and reshapes the answer wire body. **No server change** is in scope — that ships separately and **deploys first** (server-first; see Sequencing note).

**Tech Stack:** Python 3.11+, `uv`, `pytest` (`asyncio_mode="auto"` — bare `async def` tests, no `@pytest.mark.asyncio`), `respx` for HTTP mocking, `httpx`, pydantic-free dataclass models, `python_check` (ruff + pyright) for lint/format/types.

---

## CRITICAL SEQUENCING NOTE (read before starting)

This plan is **Plan 2 of 3**. It must land **AFTER** the server schema change (Plan 1) is live, because we delete the capability guardrail that protected clients from a metadata-dropping server. **Deploy order: server first, then this lib change.** Do NOT merge/release this plan's changes until a metadata-accepting server is live. (Implementation and review can proceed now; the *release* waits on the server.)

**No `git push` / PR / deploy in this plan.** Commit locally after each task. Stop at the final gate.

## Two-package gate rule

Every task ends green for the package it touches. The library (`team-pulse-lib/`) and the shim (`modules/tool-team-pulse/`) are **separate test suites**. A handful of tasks are ordered specifically so a shared symbol (`AnswerUpload.source_session_ids`, `TeamPulseUnsupportedError`) is only deleted **after** every caller across BOTH packages has stopped referencing it. Follow the task order exactly — reordering will turn a suite red.

## Test commands (memorize these)

```
# Library suite
cd team-pulse-lib && uv run pytest -q

# A single library test
cd team-pulse-lib && uv run pytest tests/test_api_methods.py::test_upload_answer_sends_exact_partner_wire_body_on_201 -v

# Shim suite
cd modules/tool-team-pulse && uv run pytest -q
```

All paths below are **relative to the repo root** `amplifier-bundle-team-pulse/`. The two `cd` roots are `team-pulse-lib/` and `modules/tool-team-pulse/`.

## What is OUT of scope (do NOT touch)

- The lib `Question` model and `_question_from_resource` — **already correct** (`{question_id, question, lookback_days}`, unwraps the lens envelope). No question changes anywhere in the lib.
- The server (`amplifier-app-team-pulse`) and the frontend — separate plans.
- `team_pulse_lib/auth.py`, `config.py`, `_version.py` — untouched.

---

## Final target shapes (reference — what we are converging on)

**`AnswerUpload` (after this plan):**
```python
@dataclass
class AnswerUpload:
    question_id: str
    user_id: str
    answer: str
    generated_at: str  # ISO-8601 UTC string
    metadata: dict[str, Any] = field(default_factory=dict)
```

**`upload_answer` wire body (after this plan) — EXACTLY these five keys, `metadata` ALWAYS present:**
```json
{"question_id": "...", "user_id": "...", "generated_at": "...", "answer": "...", "metadata": {}}
```

**`ClientInfo` (after this plan) — `server_supports_metadata` GONE:**
```python
@dataclass
class ClientInfo:
    base_url: str
    auth_mode: Literal["key", "az"]
    api_app_id: str | None
    credential_type: str
    forced: bool
    resolved: bool
```

**Deleted entirely:** `team_pulse_lib/capability.py`, `TeamPulseUnsupportedError`, the guardrail helpers, the capability probe, `server_supports_metadata` everywhere, `tests/test_guardrail.py`, `tests/test_capability.py`.

---

## Task list (14 tasks)

| # | Package | Task |
|---|---------|------|
| 1 | lib | Make `AnswerUpload.source_session_ids` optional (transitional default — unblocks green migration) |
| 2 | lib | Rewrite `upload_answer` wire body + drop the guardrail call |
| 3 | lib | Delete guardrail helper methods + `tests/test_guardrail.py` |
| 4 | lib | Strip `server_supports_metadata` from `describe()` + `ClientInfo` |
| 5 | lib | Delete capability probe + `_capability` state + `capability.py` + `tests/test_capability.py` |
| 6 | lib | Migrate library tests off `source_session_ids` |
| 7 | lib | Rewrite `examples/submit_answer.py` + its `test_examples` tests |
| 8 | lib | Update `examples/answer_generator.py` + `real_smoke_test.py` + fake-server docstring + their tests |
| 9 | shim | Rewrite `TeamPulseSubmitAnswerTool` (schema + `_call`) + its shim tests |
| 10 | shim | Clean `TeamPulseStatusTool` + `_error_result` + tool imports + its shim tests |
| 11 | lib | Delete `TeamPulseUnsupportedError` cascade (errors + `__init__` + public-surface test) |
| 12 | lib | Remove `source_session_ids` field entirely from `AnswerUpload` |
| 13 | docs | Update `context/using-team-pulse.md` |
| 14 | both | Final gate — full lib + shim suites + `python_check` |

---

### Task 1: Make `AnswerUpload.source_session_ids` optional (transitional default)

**Why:** Removing a *required* field would force every construction site (lib, examples, shim) to change in one atomic commit. Giving it a default first lets each caller stop passing it incrementally while every task stays green. The field is removed for real in Task 12.

**Files:**
- Modify: `team-pulse-lib/team_pulse_lib/models.py:32`
- Test: `team-pulse-lib/tests/test_models.py`

**Step 1: Write the failing test**

Add this test to `team-pulse-lib/tests/test_models.py` inside `class TestAnswerUpload`:

```python
    def test_source_session_ids_is_optional_transitional(self) -> None:
        # TRANSITIONAL (removed in Task 12): constructing without
        # source_session_ids must succeed and default to [].
        a = AnswerUpload(
            question_id="q1",
            user_id="u1",
            answer="I did stuff.",
            generated_at="2026-06-25T17:00:00Z",
        )
        assert a.source_session_ids == []
```

**Step 2: Run test to verify it fails**

Run: `cd team-pulse-lib && uv run pytest tests/test_models.py::TestAnswerUpload::test_source_session_ids_is_optional_transitional -v`
Expected: FAIL with `TypeError: __init__() missing 1 required positional argument: 'source_session_ids'`.

**Step 3: Write minimal implementation**

In `team-pulse-lib/team_pulse_lib/models.py`, change the `AnswerUpload` field at line 32 from:

```python
    source_session_ids: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
```

to:

```python
    source_session_ids: list[str] = field(default_factory=list)  # TRANSITIONAL — removed in Task 12
    metadata: dict[str, Any] = field(default_factory=dict)
```

**Step 4: Run test to verify it passes**

Run: `cd team-pulse-lib && uv run pytest tests/test_models.py -v`
Expected: PASS (all `TestAnswerUpload` tests green).

**Step 5: Commit**

`cd team-pulse-lib && git add team_pulse_lib/models.py tests/test_models.py && git commit -m "refactor(lib): make AnswerUpload.source_session_ids optional (transitional)"`

---

### Task 2: Rewrite `upload_answer` wire body + drop the guardrail call

**Why:** The new server speaks the partner's flat body. We send EXACTLY `{question_id, user_id, generated_at, answer, metadata}`, `metadata` always present. We also remove the `_enforce_capability_guardrail(answer)` call (the guardrail is being deleted). Removing the call means the capability probe never fires during `upload_answer`, so one describe-probe test must go.

**Files:**
- Modify: `team-pulse-lib/team_pulse_lib/client.py:608-647` (the `upload_answer` method)
- Modify: `team-pulse-lib/tests/test_api_methods.py:195-217` (rewrite the bare-submit body test)
- Modify: `team-pulse-lib/tests/test_client.py:208-234` (delete `test_describe_reports_server_supports_metadata_after_probe`)

**Step 1: Write the failing test**

In `team-pulse-lib/tests/test_api_methods.py`, **replace** the test function `test_upload_answer_bare_submit_created_true_on_201` (lines 195-217, including its `@respx.mock` decorator) with:

```python
@respx.mock
async def test_upload_answer_sends_exact_partner_wire_body_on_201():
    """upload_answer sends EXACTLY {question_id, user_id, generated_at, answer, metadata}; metadata always present; no source/respondent/source_session_ids."""
    route = respx.post(f"{BASE_URL}/api/lens/answers").mock(
        return_value=httpx.Response(201, json={"id": "ans-1", "question_id": "effective-practices"})
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.upload_answer(answer_factory(user_id="alice"))

    assert route.called
    body = json.loads(route.calls[0].request.content)
    # Exactly the five partner-canonical keys — nothing more, nothing less.
    assert set(body.keys()) == {"question_id", "user_id", "generated_at", "answer", "metadata"}
    assert body["question_id"] == "effective-practices"
    assert body["user_id"] == "alice"
    assert body["metadata"] == {}  # always present, even when empty
    # Legacy fields must be gone.
    assert "source" not in body
    assert "source_session_ids" not in body
    assert "respondent_provider" not in body
    assert "respondent_id" not in body
    # Response mapping unchanged.
    assert result.created is True
    assert result.id == "ans-1"
    assert result.question_id == "effective-practices"
```

**Step 2: Run test to verify it fails**

Run: `cd team-pulse-lib && uv run pytest tests/test_api_methods.py::test_upload_answer_sends_exact_partner_wire_body_on_201 -v`
Expected: FAIL — current body contains `source` and `respondent_provider`/`respondent_id`, and omits `metadata` (so the `set(body.keys())` assertion fails).

**Step 3: Write minimal implementation**

In `team-pulse-lib/team_pulse_lib/client.py`, **replace** the entire `upload_answer` method (lines 608-647) with:

```python
    async def upload_answer(self, answer: AnswerUpload) -> SubmittedAnswer:
        """POST /api/lens/answers — submit an AI-synthesised answer.

        Sends the partner's canonical wire body **exactly**::

            {question_id, user_id, generated_at, answer, metadata}

        ``metadata`` is ALWAYS present (an empty dict when the caller supplied
        none); session provenance lives **inside** it.  There is no ``source``
        wire field and no capability guardrail — the server persists metadata
        as of schema v1, and deploy-server-first removes the silent-loss window.

        Returns a :class:`SubmittedAnswer` with ``created=True`` on a 201
        (newly created) and ``created=False`` on an idempotent 200.

        Args:
            answer: Populated :class:`AnswerUpload` dataclass.
        """
        body: dict[str, Any] = {
            "question_id": answer.question_id,
            "user_id": answer.user_id,
            "generated_at": answer.generated_at,
            "answer": answer.answer,
            "metadata": answer.metadata,
        }

        resp = await self._post("/api/lens/answers", json_body=body)
        data = resp.json() if resp.content else {}
        if not isinstance(data, dict):
            data = {}

        return SubmittedAnswer(
            id=str(data.get("id", "")),
            question_id=str(data.get("question_id", answer.question_id)),
            created=(resp.status_code == 201),
        )
```

Then, in `team-pulse-lib/tests/test_client.py`, **delete** the entire test function `test_describe_reports_server_supports_metadata_after_probe` (lines 208-234, including its `@respx.mock` decorator and the `_BASE_URL = "https://team-pulse.test"` is shared — leave that line). This test exercised the probe-on-metadata-submit behavior we just removed.

**Step 4: Run tests to verify they pass**

Run: `cd team-pulse-lib && uv run pytest tests/test_api_methods.py tests/test_client.py -v`
Expected: PASS. The pre-existing `test_upload_answer_created_false_on_idempotent_200` and `test_upload_answer_does_not_probe_capability_for_bare_submit` still pass (still no probe). `test_describe_reports_server_supports_metadata_after_probe` is gone.

**Step 5: Commit**

`cd team-pulse-lib && git add team_pulse_lib/client.py tests/test_api_methods.py tests/test_client.py && git commit -m "feat(lib): upload_answer sends partner wire body; drop guardrail call"`

---

### Task 3: Delete guardrail helper methods + `tests/test_guardrail.py`

**Why:** After Task 2, `_guarded_fields`, `_unsupported_message`, and `_enforce_capability_guardrail` are unused. They are the only in-`client.py` users of `TeamPulseUnsupportedError`, so we also drop that import here (otherwise ruff flags an unused import).

**Files:**
- Modify: `team-pulse-lib/team_pulse_lib/client.py:556-606` (delete the three guardrail helpers)
- Modify: `team-pulse-lib/team_pulse_lib/client.py:22-27` (drop `TeamPulseUnsupportedError` from the import)
- Delete: `team-pulse-lib/tests/test_guardrail.py`

**Step 1: Write the failing test**

This is a deletion task. The "test" is the suite collecting and passing after the symbols are gone. First, confirm the current state is green so we have a clean baseline:

Run: `cd team-pulse-lib && uv run pytest tests/test_guardrail.py -q`
Expected: PASS (the guardrail tests currently pass — this is the baseline we are deliberately removing).

**Step 2: Delete the guardrail test file**

Run: `cd team-pulse-lib && git rm tests/test_guardrail.py`

Run: `cd team-pulse-lib && uv run pytest -q`
Expected: PASS — `test_guardrail.py` no longer collected; nothing else references its symbols yet (the helper methods still exist).

**Step 3: Delete the guardrail helper methods + import**

In `team-pulse-lib/team_pulse_lib/client.py`:

(a) **Delete** the whole guardrail block — from the comment header at line 556 through the end of `_enforce_capability_guardrail` at line 606. Concretely, delete these three methods and their section comment:
- the `# Capability guardrail helpers` comment block (lines 556-558),
- `_guarded_fields` (the `@staticmethod`, lines 560-577),
- `_unsupported_message` (lines 579-586),
- `_enforce_capability_guardrail` (lines 588-606).

After deletion, the `# Answer submission` comment (was line 552-554) is immediately followed by the `upload_answer` method.

(b) **Edit the import** at lines 22-27 from:

```python
from team_pulse_lib.errors import (
    TeamPulseAPIError,
    TeamPulseAuthError,
    TeamPulseConnectionError,
    TeamPulseUnsupportedError,
)
```

to:

```python
from team_pulse_lib.errors import (
    TeamPulseAPIError,
    TeamPulseAuthError,
    TeamPulseConnectionError,
)
```

**Step 4: Run tests + lint to verify green**

Run: `cd team-pulse-lib && uv run pytest -q`
Expected: PASS.

Then verify no unused-import / dead-symbol lint:

Use `python_check` on `team-pulse-lib/team_pulse_lib/client.py`.
Expected: no errors (warnings OK).

**Step 5: Commit**

`cd team-pulse-lib && git add team_pulse_lib/client.py && git rm tests/test_guardrail.py && git commit -m "refactor(lib): delete capability guardrail helpers and tests"`

---

### Task 4: Strip `server_supports_metadata` from `describe()` + `ClientInfo`

**Why:** With no capability probe, the `server_supports_metadata` field is dead. Remove it from the `ClientInfo` model and the `describe()` projection.

**Files:**
- Modify: `team-pulse-lib/team_pulse_lib/models.py:55` (remove the field from `ClientInfo`)
- Modify: `team-pulse-lib/team_pulse_lib/client.py:361-379` (remove the field from `describe()` + docstring)
- Modify: `team-pulse-lib/tests/test_models.py:61-78` (`TestClientInfo`)
- Modify: `team-pulse-lib/tests/test_client.py:185-197` (`test_describe_before_context_entry_is_unresolved_and_unprobed`)

**Step 1: Write the failing test**

In `team-pulse-lib/tests/test_models.py`, **replace** `class TestClientInfo` (lines 61-78) with:

```python
class TestClientInfo:
    def test_full_shape(self) -> None:
        ci = ClientInfo(
            base_url="https://example.com",
            auth_mode="key",
            api_app_id=None,
            credential_type="api_key",
            forced=False,
            resolved=False,
        )
        assert ci.base_url == "https://example.com"
        assert ci.auth_mode == "key"
        assert ci.api_app_id is None
        assert ci.credential_type == "api_key"
        assert ci.forced is False
        assert ci.resolved is False

    def test_server_supports_metadata_field_is_gone(self) -> None:
        field_names = {f.name for f in dataclasses.fields(ClientInfo)}
        assert "server_supports_metadata" not in field_names
```

**Step 2: Run test to verify it fails**

Run: `cd team-pulse-lib && uv run pytest tests/test_models.py::TestClientInfo -v`
Expected: FAIL — `test_full_shape` raises `TypeError: __init__() missing 1 required positional argument: 'server_supports_metadata'` (the field still exists and has no default).

**Step 3: Write minimal implementation**

(a) In `team-pulse-lib/team_pulse_lib/models.py`, delete line 55 so `ClientInfo` ends at `resolved: bool`:

```python
@dataclass
class ClientInfo:
    """Snapshot of the resolved client configuration and credential state."""

    base_url: str
    auth_mode: Literal["key", "az"]  # active identity mode
    api_app_id: str | None  # None when auth_mode == "key"
    credential_type: str  # "api_key" | "azure_default_credential"
    forced: bool  # True iff an explicit force override is active
    resolved: bool  # False before __aenter__, True after credential materialises
```

(b) In `team-pulse-lib/team_pulse_lib/client.py`, **replace** the `describe` method (lines 361-379) with:

```python
    async def describe(self) -> ClientInfo:
        """Return a provenance-only snapshot of the resolved client configuration.

        **Never makes a network call; never exposes secrets.**  Safe to call at
        any point — before or after entering the async context manager.
        """
        return ClientInfo(
            base_url=self._base_url,
            auth_mode=self._auth_mode,
            api_app_id=self._api_app_id,
            credential_type=self._credential_type,
            forced=self._forced,
            resolved=self._resolved,
        )
```

(c) In `team-pulse-lib/tests/test_client.py`, in `test_describe_before_context_entry_is_unresolved_and_unprobed` (lines 185-197), **delete** the line:

```python
    assert info.server_supports_metadata is None
```

**Step 4: Run tests to verify they pass**

Run: `cd team-pulse-lib && uv run pytest tests/test_models.py tests/test_client.py -v`
Expected: PASS.

**Step 5: Commit**

`cd team-pulse-lib && git add team_pulse_lib/models.py team_pulse_lib/client.py tests/test_models.py tests/test_client.py && git commit -m "refactor(lib): remove server_supports_metadata from ClientInfo and describe()"`

---

### Task 5: Delete capability probe + state + `capability.py` + `tests/test_capability.py`

**Why:** Nothing references the capability cache anymore (guardrail gone in Task 3, `describe()` cleaned in Task 4). Delete the probe methods, the `_capability` instance state, the `capability.py` module, its import, and its test file.

**Files:**
- Modify: `team-pulse-lib/team_pulse_lib/client.py:21` (remove the `capability` import)
- Modify: `team-pulse-lib/team_pulse_lib/client.py:99` (remove `self._capability` init)
- Modify: `team-pulse-lib/team_pulse_lib/client.py:321-333` (delete `_probe_capability` + `_ensure_fresh_capability`)
- Delete: `team-pulse-lib/team_pulse_lib/capability.py`
- Delete: `team-pulse-lib/tests/test_capability.py`

**Step 1: Establish the baseline**

Run: `cd team-pulse-lib && uv run pytest tests/test_capability.py -q`
Expected: PASS (baseline we are deliberately removing).

**Step 2: Delete the capability test file**

Run: `cd team-pulse-lib && git rm tests/test_capability.py`

**Step 3: Remove the probe + state + import, then delete the module**

In `team-pulse-lib/team_pulse_lib/client.py`:

(a) **Delete** the import at line 21:

```python
from team_pulse_lib.capability import CapabilityCache, parse_capabilities
```

(b) **Delete** the `_capability` init line (line 99) inside `__init__`:

```python
        self._capability: CapabilityCache = CapabilityCache()
```

(c) **Delete** the capability-probe section (lines 321-333) — the comment header and both methods:

```python
    # ------------------------------------------------------------------
    # Capability probe
    # ------------------------------------------------------------------

    async def _probe_capability(self) -> None:
        """Fetch ``GET /api/lens/info`` and populate the capability cache."""
        resp = await self._get("/api/lens/info")
        self._capability.store(parse_capabilities(resp.json()))

    async def _ensure_fresh_capability(self) -> None:
        """Probe the server if the capability cache is stale or empty."""
        if not self._capability.is_fresh():
            await self._probe_capability()
```

(d) Delete the module file:

Run: `cd team-pulse-lib && git rm team_pulse_lib/capability.py`

**Step 4: Run tests + lint to verify green**

Run: `cd team-pulse-lib && uv run pytest -q`
Expected: PASS.

Use `python_check` on `team-pulse-lib/team_pulse_lib/client.py`.
Expected: no errors (no unused imports, no references to `CapabilityCache`/`parse_capabilities`/`_capability`).

**Step 5: Commit**

`cd team-pulse-lib && git add team_pulse_lib/client.py && git rm team_pulse_lib/capability.py tests/test_capability.py && git commit -m "refactor(lib): delete capability probe, cache, and capability.py module"`

---

### Task 6: Migrate library tests off `source_session_ids`

**Why:** Stop the library's own tests from passing `source_session_ids` so that Task 12 can delete the field. The field is still present (optional, since Task 1), so this is a safe, green refactor.

**Files:**
- Modify: `team-pulse-lib/tests/test_models.py` (the two `TestAnswerUpload` constructions at lines 22-48)
- Modify: `team-pulse-lib/tests/test_api_methods.py:177-187` (`answer_factory` defaults)
- Modify: `team-pulse-lib/tests/test_client.py:27` (remove the now-unused `AnswerUpload` import)

**Step 1: Update the constructions (no new test — this is a green refactor of existing tests)**

(a) In `team-pulse-lib/tests/test_models.py`, in `test_metadata_defaults_to_empty_dict` (lines 22-30) **remove** the `source_session_ids=[]` line so it reads:

```python
    def test_metadata_defaults_to_empty_dict(self) -> None:
        a = AnswerUpload(
            question_id="q1",
            user_id="u1",
            answer="I did stuff.",
            generated_at="2026-06-25T17:00:00Z",
        )
        assert a.metadata == {}
```

In `test_metadata_not_shared_between_instances` (lines 32-48) **remove** both `source_session_ids=[]` lines:

```python
    def test_metadata_not_shared_between_instances(self) -> None:
        a1 = AnswerUpload(
            question_id="q1",
            user_id="u1",
            answer="Answer 1",
            generated_at="2026-06-25T17:00:00Z",
        )
        a2 = AnswerUpload(
            question_id="q2",
            user_id="u2",
            answer="Answer 2",
            generated_at="2026-06-25T18:00:00Z",
        )
        a1.metadata["key"] = "value"
        assert "key" not in a2.metadata, "metadata must not be shared between instances"
```

(b) In `team-pulse-lib/tests/test_api_methods.py`, in `answer_factory` (lines 177-187) **remove** the `"source_session_ids": []` default:

```python
def answer_factory(**kwargs: object) -> AnswerUpload:
    """Return an AnswerUpload with bare-submit defaults (empty user_id, empty metadata)."""
    defaults: dict[str, object] = {
        "question_id": "effective-practices",
        "user_id": "",
        "answer": "AI synthesised answer text",
        "generated_at": "2026-06-25T17:00:00Z",
    }
    defaults.update(kwargs)
    return AnswerUpload(**defaults)  # type: ignore[arg-type]
```

(c) In `team-pulse-lib/tests/test_client.py`, the only `AnswerUpload` usage was in the test deleted in Task 2. **Edit** the import at line 27 from:

```python
from team_pulse_lib.models import AnswerUpload, ClientInfo
```

to:

```python
from team_pulse_lib.models import ClientInfo
```

**Step 2: Run tests to verify they pass**

Run: `cd team-pulse-lib && uv run pytest tests/test_models.py tests/test_api_methods.py tests/test_client.py -v`
Expected: PASS.

**Step 3: Lint**

Use `python_check` on `team-pulse-lib/tests/test_client.py`.
Expected: no unused-import error for `AnswerUpload`.

**Step 4: Commit**

`cd team-pulse-lib && git add tests/test_models.py tests/test_api_methods.py tests/test_client.py && git commit -m "test(lib): stop passing source_session_ids in library tests"`

---

### Task 7: Rewrite `examples/submit_answer.py` + its `test_examples` tests

**Why:** The example currently demonstrates the deleted guardrail (3 scenarios, two server postures, `TeamPulseUnsupportedError`). Replace it with a clean two-submit demo (bare + with-metadata), both succeeding, sessions carried **inside** `metadata`. This also removes the example's reference to `TeamPulseUnsupportedError` so Task 11 can delete the class.

**Files:**
- Rewrite: `team-pulse-lib/examples/submit_answer.py`
- Modify: `team-pulse-lib/tests/test_examples.py` (the `submit_answer` test block, lines 124-199, and the import at line 29)

**Step 1: Write the failing test**

In `team-pulse-lib/tests/test_examples.py`:

(a) Change the import at line 29-30 from:

```python
from team_pulse_lib import DEFAULT_API_APP_ID, TeamPulseUnsupportedError
from team_pulse_lib.models import Question, SubmittedAnswer
```

to:

```python
from team_pulse_lib import DEFAULT_API_APP_ID
from team_pulse_lib.models import Question, SubmittedAnswer
```

(b) **Replace** the entire `submit_answer tests` section (lines 124-199 — the banner comment block through the end of `test_fake_server_recorded_bare_and_meta_answers`) with:

```python
# ===========================================================================
# submit_answer tests
# ===========================================================================


async def test_bare_submit_returns_submitted_answer_created_true() -> None:
    """Bare submit (no metadata) returns SubmittedAnswer(created=True)."""
    with FakeTeamPulseServer() as url:
        result = await sa_ex.main(base_url=url, api_key=_API_KEY)

    bare = result["bare"]
    assert isinstance(bare, SubmittedAnswer)
    assert bare.created is True
    assert bare.question_id == "higher-level-work"


async def test_metadata_submit_succeeds_and_carries_sessions_in_metadata() -> None:
    """A submit WITH metadata succeeds; session ids live inside metadata."""
    server = FakeTeamPulseServer()
    url = server.start()
    try:
        result = await sa_ex.main(base_url=url, api_key=_API_KEY)

        meta = result["meta_submit"]
        assert isinstance(meta, SubmittedAnswer)
        assert meta.created is True

        # The recorded body for the meta submit carries sessions inside metadata.
        recorded = next(a for a in server.submitted_answers if a.get("metadata"))
        assert "source_session_ids" in recorded["metadata"]
    finally:
        server.stop()
```

**Step 2: Run test to verify it fails**

Run: `cd team-pulse-lib && uv run pytest tests/test_examples.py -q`
Expected: FAIL — the new tests call `sa_ex.main(base_url=...)`, but the current `submit_answer.main` signature is `main(*, base_url_no_meta, base_url_with_meta, api_key)`, and `result["meta_submit"]` carries no metadata in the recorded body yet.

**Step 3: Rewrite the example**

**Replace the entire contents** of `team-pulse-lib/examples/submit_answer.py` with:

```python
# SPDX-License-Identifier: MIT
"""Example: submitting answers to Team Pulse (schema v1).

Two scenarios, both succeeding against the same server:

1. **BARE SUBMIT** — no ``user_id``, empty ``metadata``.
2. **METADATA SUBMIT** — a ``user_id`` plus a ``metadata`` bag that carries
   session provenance (``source_session_ids``) and any other opaque fields.

There is no capability guardrail: the schema-v1 server persists ``metadata``
verbatim, and the bundle deploys server-first so a metadata-sending client is
never ahead of the server.

Usage (self-contained — auto-starts the stdlib fake server)::

    uv run python examples/submit_answer.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from team_pulse_lib import TeamPulseClient
from team_pulse_lib.models import AnswerUpload, SubmittedAnswer


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def main(*, base_url: str, api_key: str = "tp_demo") -> dict:
    """Run a bare submit and a metadata submit; return results for assertions.

    Args:
        base_url: Team Pulse server URL.
        api_key: API key starting with ``tp_``.  Overridden by the
            ``AMPLIFIER_TEAM_PULSE_KEY`` env var when set.

    Returns:
        ``dict`` with ``bare`` and ``meta_submit`` (both
        :class:`~team_pulse_lib.models.SubmittedAnswer`).
    """
    key: str = os.environ.get("AMPLIFIER_TEAM_PULSE_KEY") or api_key

    # -----------------------------------------------------------------------
    # Scenario 1: BARE SUBMIT — empty user_id, empty metadata
    # -----------------------------------------------------------------------
    print("\n=== Scenario 1: Bare Submit ===")
    bare_payload = AnswerUpload(
        question_id="higher-level-work",
        user_id="",
        answer=(
            "Shipped the auth refactor, reviewed three pull requests, "
            "and unblocked two teammates stuck on the migration script."
        ),
        generated_at=_now_iso(),
    )
    print(f"  question_id : {bare_payload.question_id}")
    print(f"  metadata    : {bare_payload.metadata}  (empty)")

    bare_result: SubmittedAnswer
    async with TeamPulseClient.connect(base_url=base_url, key=key) as client:
        bare_result = await client.upload_answer(bare_payload)
    print(
        f"  -> SubmittedAnswer(id={bare_result.id!r}, "
        f"question_id={bare_result.question_id!r}, created={bare_result.created})"
    )

    # -----------------------------------------------------------------------
    # Scenario 2: METADATA SUBMIT — user_id + metadata (sessions live inside)
    # -----------------------------------------------------------------------
    print("\n=== Scenario 2: Metadata Submit ===")
    meta_payload = AnswerUpload(
        question_id="higher-level-work",
        user_id="alice",
        answer="Answer with full metadata and user attribution.",
        generated_at=_now_iso(),
        metadata={
            "source_session_ids": ["session-xyz789"],
            "model": "claude-opus-4-6",
            "confidence": 0.92,
        },
    )
    print(f"  question_id : {meta_payload.question_id}")
    print(f"  user_id     : {meta_payload.user_id!r}")
    print(f"  metadata    : {meta_payload.metadata}")

    meta_result: SubmittedAnswer
    async with TeamPulseClient.connect(base_url=base_url, key=key) as client:
        meta_result = await client.upload_answer(meta_payload)
    print(
        f"  -> SubmittedAnswer(id={meta_result.id!r}, "
        f"question_id={meta_result.question_id!r}, created={meta_result.created})"
    )

    print("\n=== Summary ===")
    print("  1. Bare submit     -> created=True")
    print("  2. Metadata submit -> created (sessions carried inside metadata)")
    print()

    return {"bare": bare_result, "meta_submit": meta_result}


if __name__ == "__main__":
    from fake_team_pulse_server import FakeTeamPulseServer

    with FakeTeamPulseServer() as _url:
        asyncio.run(main(base_url=_url))
```

> Note: the bare and metadata submits use the same `question_id`. The fake server is idempotent per `question_id`, so the metadata submit returns 200 (`created=False`) only if a bare submit for that id already landed on the **same** server instance. Here each `main()` run uses one fresh server and the bare submit lands first, so the metadata submit is a 200 idempotent echo — but it still records the metadata body. The test asserts on the recorded metadata, not on `created`. If you prefer both to be 201, give the metadata submit a distinct `question_id` (e.g. `effective-practices`) — both are valid; keep it simple.

**Step 4: Run tests to verify they pass**

Run: `cd team-pulse-lib && uv run pytest tests/test_examples.py -q`
Expected: PASS.

> If `test_metadata_submit_succeeds_and_carries_sessions_in_metadata` fails because the bare and metadata submits collide on `question_id` (idempotent 200, metadata still recorded), the `next(...)` lookup still finds the metadata-bearing record — the assertion is on the recorded body, not `created`. If you switched the metadata submit to a distinct `question_id`, update the example accordingly and re-run.

**Step 5: Commit**

`cd team-pulse-lib && git add examples/submit_answer.py tests/test_examples.py && git commit -m "docs(lib): rewrite submit_answer example for schema v1 (no guardrail)"`

---

### Task 8: Update `examples/answer_generator.py` + `real_smoke_test.py` + fake-server docstring + their tests

**Why:** Remove the last `source_session_ids` constructions and the last `TeamPulseUnsupportedError` reference from the examples package, and clean the stale `parse_capabilities` mention in the fake server's docstring.

**Files:**
- Modify: `team-pulse-lib/examples/answer_generator.py:104-111` (drop `source_session_ids`, move into `metadata`)
- Modify: `team-pulse-lib/examples/real_smoke_test.py` (remove the guardrail step + `TeamPulseUnsupportedError` import; sessions into metadata)
- Modify: `team-pulse-lib/examples/fake_team_pulse_server.py` (docstring cleanup only)
- Modify: `team-pulse-lib/tests/test_examples.py` (answer_generator tests still pass — verify only)

**Step 1: Update `answer_generator.py`**

In `team-pulse-lib/examples/answer_generator.py`, **replace** the `AnswerUpload(...)` construction (lines 104-111) with:

```python
            payload = AnswerUpload(
                question_id=q.question_id,
                user_id=user_id,  # empty by default -> bare submit
                answer=answer_text,
                generated_at=generated_at,
                metadata={"source_session_ids": ["example-session-generator-001"]},
            )
```

**Step 2: Update `real_smoke_test.py`**

In `team-pulse-lib/examples/real_smoke_test.py`:

(a) Change the import (lines 41-42) from:

```python
from team_pulse_lib import AnswerUpload, TeamPulseClient
from team_pulse_lib.errors import TeamPulseUnsupportedError
```

to:

```python
from team_pulse_lib import AnswerUpload, TeamPulseClient
```

(b) **Replace** the guardrail section (lines 83-98 — the `# 4. Guardrail:` comment through the `except TeamPulseUnsupportedError` block) with a metadata-submit demo:

```python
        # 4. Metadata submit: schema v1 persists metadata; sessions live inside it.
        print("\n[metadata submit] posting an answer WITH metadata (sessions inside)")
        meta = AnswerUpload(
            question_id=target,
            user_id="smoke-test",
            answer="[SMOKE] metadata-bearing submit — sessions carried in metadata",
            generated_at=_utc_now_iso(),
            metadata={"source_session_ids": [], "smoke": True},
        )
        meta_result = await client.upload_answer(meta)
        print(
            f"  SubmittedAnswer(id={meta_result.id!r}, "
            f"question_id={meta_result.question_id!r}, created={meta_result.created})"
        )
```

(c) **Replace** the bare-submit block (lines 100-113) — remove the `source_session_ids=[]` argument:

```python
        # 5. Opt-in real bare write.
        if do_submit:
            print("\n[submit] posting one REAL bare answer (no metadata) -- this WRITES data")
            bare = AnswerUpload(
                question_id=target,
                user_id="",
                answer="[SMOKE TEST] schema-v1 real-server submit verification.",
                generated_at=_utc_now_iso(),
            )
            result = await client.upload_answer(bare)
            print(f"  SubmittedAnswer(id={result.id!r}, question_id={result.question_id!r}, created={result.created})")
        else:
            print("\n[submit] skipped (pass --submit to POST one real bare answer).")
```

(d) Update the module docstring (lines 22-31): remove the `4. guardrail` bullet and its description; renumber so the read-only checks are `describe`, `whoami`, `fetch_questions`, and the opt-in write is `--submit`. (Prose-only; keep it short and accurate.)

**Step 3: Clean the fake-server docstring**

In `team-pulse-lib/examples/fake_team_pulse_server.py`, the module docstring (lines 17-23) and the `advertise_metadata` arg docstring (lines 200-205) reference `team_pulse_lib.capability.parse_capabilities`, which no longer exists. **Update** those prose references to drop the `parse_capabilities` mention (e.g. "When ``False`` (default), the info payload has no ``capabilities`` key."). Do **not** change any server behavior or the `advertise_metadata` flag — only the prose. (`advertise_metadata` is now decorative since the client never probes; leaving it is harmless and keeps the server reusable.)

**Step 4: Run tests to verify they pass**

Run: `cd team-pulse-lib && uv run pytest tests/test_examples.py -q`
Expected: PASS — the `answer_generator` tests (lines 207-248) are behavior-stable (one answer per active question; `source_session_ids` moved into `metadata` doesn't change counts or ids). `real_smoke_test.py` has no pytest tests (manual script).

Also sanity-run the scripts headless:

Run: `cd team-pulse-lib && uv run python examples/submit_answer.py && uv run python examples/answer_generator.py`
Expected: both print their summaries and exit 0.

**Step 5: Lint + commit**

Use `python_check` on `team-pulse-lib/examples/`.
Expected: no errors.

`cd team-pulse-lib && git add examples/ tests/test_examples.py && git commit -m "docs(lib): move session ids into metadata across examples; drop guardrail demo"`

---

### Task 9: Rewrite `TeamPulseSubmitAnswerTool` (schema + `_call`) + its shim tests

**Why:** The shim's submit tool currently requires `source_session_ids` and builds `AnswerUpload` with it. Move to the new contract: drop `source_session_ids`, accept an optional `metadata` object (session ids live inside it), and stop importing/handling `TeamPulseUnsupportedError` from this test file.

**Files:**
- Modify: `modules/tool-team-pulse/amplifier_module_tool_team_pulse/tool.py:552-634` (`TeamPulseSubmitAnswerTool` docstring, description, `input_schema`, `_call`)
- Modify: `modules/tool-team-pulse/tests/test_submit_answer_shim.py`

**Step 1: Write the failing tests**

In `modules/tool-team-pulse/tests/test_submit_answer_shim.py`:

(a) Change the import (lines 26-33) from:

```python
from team_pulse_lib import (
    AnswerUpload,
    SubmittedAnswer,
    TeamPulseUnsupportedError,
)
from team_pulse_lib import (
    TeamPulseClient as _LibClient,
)
```

to:

```python
from team_pulse_lib import (
    AnswerUpload,
    SubmittedAnswer,
)
from team_pulse_lib import (
    TeamPulseClient as _LibClient,
)
```

(b) Change `_VALID_INPUT` (lines 59-65) to the new shape (no `source_session_ids`; sessions go inside an optional `metadata`):

```python
_VALID_INPUT: dict = {
    "question_id": _QUESTION_ID,
    "user_id": _USER_ID,
    "answer": _ANSWER,
    "metadata": {"source_session_ids": _SESSION_IDS},
    "generated_at": _GENERATED_AT,
}
```

(c) **Replace** `test_answer_upload_carries_all_input_fields` (lines 103-115) with:

```python
async def test_answer_upload_carries_all_input_fields():
    """AnswerUpload passed to upload_answer must carry all input fields; sessions live in metadata."""
    mock_client = _make_mock_client()
    tool = TeamPulseSubmitAnswerTool(mock_client)
    await tool.execute(_VALID_INPUT)

    arg: AnswerUpload = mock_client.upload_answer.call_args[0][0]
    assert isinstance(arg, AnswerUpload)
    assert arg.question_id == _QUESTION_ID
    assert arg.user_id == _USER_ID
    assert arg.answer == _ANSWER
    assert arg.generated_at == _GENERATED_AT
    assert arg.metadata == {"source_session_ids": _SESSION_IDS}
```

(d) **Replace** `test_answer_upload_metadata_defaults_to_empty_dict` (lines 118-125) with a version that checks the default when `metadata` is omitted:

```python
async def test_answer_upload_metadata_defaults_to_empty_dict():
    """When no metadata is supplied, AnswerUpload.metadata is {}."""
    mock_client = _make_mock_client()
    tool = TeamPulseSubmitAnswerTool(mock_client)
    bare_input = {k: v for k, v in _VALID_INPUT.items() if k != "metadata"}
    await tool.execute(bare_input)

    arg: AnswerUpload = mock_client.upload_answer.call_args[0][0]
    assert arg.metadata == {}
```

(e) **Delete** the three guardrail tests (lines 162-203): `test_unsupported_surfaces_as_failure`, `test_unsupported_error_code_is_unsupported`, `test_unsupported_message_contains_phase_1` (and their `# Scenario 3` banner comment at lines 162-164).

(f) **Replace** the schema tests `test_schema_required_fields_match` (lines 233-241) and `test_schema_source_session_ids_is_array_of_strings` (lines 256-260) with:

```python
def test_schema_required_fields_match():
    """Required fields must be exactly the 4 caller-supplied fields (no source_session_ids)."""
    assert set(_schema()["required"]) == {
        "question_id",
        "user_id",
        "answer",
        "generated_at",
    }


def test_schema_has_no_source_session_ids():
    """source_session_ids is gone — sessions now live inside metadata."""
    assert "source_session_ids" not in _schema()["properties"]


def test_schema_allows_optional_metadata():
    """metadata is an optional object property (sessions live inside it)."""
    props = _schema()["properties"]
    assert "metadata" in props
    assert props["metadata"]["type"] == "object"
    assert "metadata" not in _schema()["required"]
```

Leave `test_schema_additional_properties_false`, `test_schema_question_id_has_bare_slug_pattern`, and `test_schema_has_no_source_field` unchanged.

**Step 2: Run tests to verify they fail**

Run: `cd modules/tool-team-pulse && uv run pytest tests/test_submit_answer_shim.py -q`
Expected: FAIL — the current schema still requires `source_session_ids` and has no `metadata` property; `_call` still reads `input["source_session_ids"]` (KeyError on the new `_VALID_INPUT`).

**Step 3: Rewrite the submit tool**

In `modules/tool-team-pulse/amplifier_module_tool_team_pulse/tool.py`, **replace** the `TeamPulseSubmitAnswerTool` class (lines 552-634) with:

```python
class TeamPulseSubmitAnswerTool(_LensTool):
    """Submit a session-mined answer to a team-pulse reflection question.
    Use this to record an AI-generated answer attributed to a specific user,
    synthesized from their Context Intelligence sessions.

    question_id is the BARE SLUG (e.g. 'higher-level-work'), NOT the
    hierarchical 'questions/<slug>' form — strip the 'questions/' prefix if
    you have it. Discover valid slugs via team_pulse_resources(type='question')
    and use the data.id field (or strip the prefix from the list-envelope id).

    user_id is the github username of the person the answer is about; the
    bundle records it as a github-namespaced identity (the API stores it
    verbatim and resolves to a team member at read time). metadata is an
    optional opaque bag — session provenance (source_session_ids), timing,
    and any other context live INSIDE it. generated_at is the ISO-8601
    timestamp when the answer was generated."""

    name = "team_pulse_submit_answer"
    description = (
        "Submit a session-mined answer to a team-pulse reflection question. "
        "Use this to record an AI-generated answer attributed to a specific user, "
        "synthesized from their Context Intelligence sessions.\n\n"
        "question_id is the BARE SLUG (e.g. 'higher-level-work'), NOT the "
        "hierarchical 'questions/<slug>' form — strip the 'questions/' prefix if "
        "you have it. Discover valid slugs via team_pulse_resources(type='question') "
        "and use the data.id field (or strip the prefix from the list-envelope id).\n\n"
        "user_id is the github username of the person the answer is about; the "
        "bundle records it as a github-namespaced identity (the API stores it "
        "verbatim and resolves to a team member at read time). "
        "metadata is an optional opaque bag — session provenance "
        "(source_session_ids), timing, and any other context live INSIDE it. "
        "generated_at is the ISO-8601 timestamp when the answer was generated."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question_id": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9-]*$",
                    "description": (
                        "Bare question slug (e.g. 'higher-level-work'). Hierarchical 'questions/<slug>' is rejected."
                    ),
                },
                "user_id": {
                    "type": "string",
                    "description": "GitHub username of the person the answer is about.",
                },
                "answer": {
                    "type": "string",
                    "minLength": 1,
                    "description": "The answer body.",
                },
                "generated_at": {
                    "type": "string",
                    "description": "ISO-8601 timestamp when the answer was generated.",
                },
                "metadata": {
                    "type": "object",
                    "description": (
                        "Optional opaque bag stored verbatim by the server. Session "
                        "provenance lives here as source_session_ids (array of "
                        "Context Intelligence session IDs); may also carry timing, "
                        "model, confidence, etc."
                    ),
                },
            },
            "required": ["question_id", "user_id", "answer", "generated_at"],
            "additionalProperties": False,
        }

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        upload = AnswerUpload(
            question_id=input["question_id"],
            user_id=input["user_id"],
            answer=input["answer"],
            generated_at=input["generated_at"],
            metadata=input.get("metadata") or {},
        )
        result = await client.upload_answer(upload)
        return ToolResult(success=True, output=_as_jsonable(result))
```

**Step 4: Run tests to verify they pass**

Run: `cd modules/tool-team-pulse && uv run pytest tests/test_submit_answer_shim.py -q`
Expected: PASS.

**Step 5: Commit**

`cd modules/tool-team-pulse && git add amplifier_module_tool_team_pulse/tool.py tests/test_submit_answer_shim.py && git commit -m "feat(shim): submit tool drops source_session_ids, accepts optional metadata"`

---

### Task 10: Clean `TeamPulseStatusTool` + `_error_result` + tool imports + its shim tests

**Why:** Remove `server_supports_metadata` from the status tool output (the `ClientInfo` field is gone), and remove the `TeamPulseUnsupportedError` import + its `_error_result` branch. After this task the shim references `TeamPulseUnsupportedError` nowhere, so Task 11 can delete the class.

**Files:**
- Modify: `modules/tool-team-pulse/amplifier_module_tool_team_pulse/tool.py:22-29` (import)
- Modify: `modules/tool-team-pulse/amplifier_module_tool_team_pulse/tool.py:135-204` (`_error_result` — drop the unsupported branch + docstring line)
- Modify: `modules/tool-team-pulse/amplifier_module_tool_team_pulse/tool.py:637-675` (`TeamPulseStatusTool` docstring, description, output dict)
- Modify: `modules/tool-team-pulse/tests/test_status.py`

**Step 1: Write the failing tests**

In `modules/tool-team-pulse/tests/test_status.py`:

(a) Change `_CLIENT_INFO_AZ` (lines 34-42) to drop the `server_supports_metadata` argument:

```python
_CLIENT_INFO_AZ = ClientInfo(
    base_url=_BASE_URL,
    auth_mode="az",
    api_app_id=_API_APP_ID,
    credential_type="azure_default_credential",
    forced=False,
    resolved=True,
)
```

(b) **Replace** `test_status_returns_server_supports_metadata_false` (lines 132-136) with a test asserting the field is gone from the output:

```python
async def test_status_output_has_no_server_supports_metadata() -> None:
    """server_supports_metadata is gone — it must not appear in the status output."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert "server_supports_metadata" not in result.output
```

**Step 2: Run tests to verify they fail**

Run: `cd modules/tool-team-pulse && uv run pytest tests/test_status.py -q`
Expected: FAIL — `ClientInfo(...)` without `server_supports_metadata` raises `TypeError` only if the lib field still existed; since Task 4 removed it, the FAIL is instead in the **old** assertions still present elsewhere? No — at this point the lib field is already gone (Task 4). The current `test_status.py` still constructs `_CLIENT_INFO_AZ` WITH the field at module import → collection error. After edit (a), collection succeeds; `test_status_output_has_no_server_supports_metadata` then FAILS because the tool's output dict still includes `"server_supports_metadata": info.server_supports_metadata` (an `AttributeError` at runtime, surfaced as a failing/erroring test).

> Reality check: because Task 4 already deleted `ClientInfo.server_supports_metadata`, the shim suite is currently RED at module-import for `test_status.py` (it constructs the field) AND the tool's `describe()` projection references `info.server_supports_metadata`. That is expected — this task is where we fix the shim. Edits (a) and (b) plus Step 3 bring it green.

**Step 3: Clean the tool**

In `modules/tool-team-pulse/amplifier_module_tool_team_pulse/tool.py`:

(a) Edit the import (lines 22-29) from:

```python
from team_pulse_lib import (
    AnswerUpload,
    TeamPulseAPIError,
    TeamPulseClient,
    TeamPulseConnectionError,
    TeamPulseError,
    TeamPulseUnsupportedError,
)
```

to:

```python
from team_pulse_lib import (
    AnswerUpload,
    TeamPulseAPIError,
    TeamPulseClient,
    TeamPulseConnectionError,
    TeamPulseError,
)
```

(b) In `_error_result`, **delete** the unsupported branch (lines 178-182):

```python
    if isinstance(exc, TeamPulseUnsupportedError):
        return ToolResult(
            success=False,
            error={"code": "unsupported", "message": str(exc), "status": 422},
        )
```

Also update the `_error_result` docstring: delete the numbered item "3. ``TeamPulseUnsupportedError`` -> ``{code: 'unsupported', status: 422}``." (lines 148) and renumber the remaining items 3-5 (it is fine to leave the prose numbering approximate, but remove the unsupported line so the docstring doesn't describe a deleted branch).

(c) **Replace** the `TeamPulseStatusTool` class (lines 637-675) with:

```python
class TeamPulseStatusTool(_LensTool):
    """Return provenance-only client configuration — never any secret.

    Lists: base_url, auth_mode ('key' | 'az'), api_app_id, credential_type,
    forced, resolved.  The response is built from an explicit field allow-list
    so that a future ClientInfo field that happens to carry a secret (key,
    token, etc.) cannot leak through a blanket spread.
    """

    name = "team_pulse_status"
    description = (
        "Report THIS client's locally-resolved config (no network call, no secrets). "
        "Lists: base_url (the team-pulse endpoint you are pointed at), "
        "auth_mode ('key' | 'az'), credential_type, api_app_id, forced, resolved. "
        "Answers 'which server am I talking to and how am I authenticating?' and "
        "works even when auth is broken or the server is unreachable — use it to "
        "diagnose auth/connection failures. For the SERVER's own documented "
        "capabilities and endpoints, use team_pulse_info instead."
    )

    # input_schema inherits the closed empty object from _LensTool:
    # {type: object, properties: {}, additionalProperties: False}

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        info = await client.describe()
        # Explicit allow-list — never spread info.__dict__ or asdict(info).
        # This ensures no future secret field (key, token, etc.) can leak.
        return ToolResult(
            success=True,
            output={
                "base_url": info.base_url,
                "auth_mode": info.auth_mode,
                "api_app_id": info.api_app_id,
                "credential_type": info.credential_type,
                "forced": info.forced,
                "resolved": info.resolved,
            },
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd modules/tool-team-pulse && uv run pytest tests/test_status.py -q`
Expected: PASS.

Then run the whole shim suite to confirm nothing else broke:

Run: `cd modules/tool-team-pulse && uv run pytest -q`
Expected: PASS. (`test_init_exports.py` is unaffected — it never listed `TeamPulseUnsupportedError`.)

**Step 5: Lint + commit**

Use `python_check` on `modules/tool-team-pulse/amplifier_module_tool_team_pulse/tool.py`.
Expected: no errors (no unused `TeamPulseUnsupportedError` import).

`cd modules/tool-team-pulse && git add amplifier_module_tool_team_pulse/tool.py tests/test_status.py && git commit -m "refactor(shim): drop server_supports_metadata + TeamPulseUnsupportedError from status/error mapping"`

---

### Task 11: Delete `TeamPulseUnsupportedError` cascade

**Why:** No code in either package references it now (lib: Tasks 2-3, 7-8; shim: Tasks 9-10). Delete the class and its exports.

**Files:**
- Modify: `team-pulse-lib/team_pulse_lib/errors.py:39-45` (delete the class)
- Modify: `team-pulse-lib/team_pulse_lib/__init__.py:21-27` (import) and `:44` (`__all__`)
- Modify: `team-pulse-lib/tests/test_public_surface.py` (`_EXPECTED` + docstring count)

**Step 1: Write the failing test**

In `team-pulse-lib/tests/test_public_surface.py`:

(a) Delete `"TeamPulseUnsupportedError",` from the `_EXPECTED` list (line 36).

(b) Update the module docstring count (lines 7-13): change "The 18 names" to "The 17 names" and "5 exception classes" to "4 exception classes".

Add a guard test at the end of the file:

```python
def test_unsupported_error_is_gone() -> None:
    """TeamPulseUnsupportedError must no longer be importable from team_pulse_lib."""
    assert not hasattr(tpl, "TeamPulseUnsupportedError")
```

**Step 2: Run test to verify it fails**

Run: `cd team-pulse-lib && uv run pytest tests/test_public_surface.py -q`
Expected: FAIL — `test_unsupported_error_is_gone` fails (the symbol is still exported), and `test_all_matches_expected` fails (`__all__` still has the extra name vs the trimmed `_EXPECTED`).

**Step 3: Delete the class + exports**

(a) In `team-pulse-lib/team_pulse_lib/errors.py`, delete the entire `TeamPulseUnsupportedError` class (lines 39-45). The file ends at `TeamPulseConnectionError`.

(b) In `team-pulse-lib/team_pulse_lib/__init__.py`, edit the errors import (lines 21-27) from:

```python
from team_pulse_lib.errors import (
    TeamPulseAPIError,
    TeamPulseAuthError,
    TeamPulseConnectionError,
    TeamPulseError,
    TeamPulseUnsupportedError,
)
```

to:

```python
from team_pulse_lib.errors import (
    TeamPulseAPIError,
    TeamPulseAuthError,
    TeamPulseConnectionError,
    TeamPulseError,
)
```

and delete `"TeamPulseUnsupportedError",` from `__all__` (line 44). Optionally update the Phase-0 contract docstring (lines 7-11) if it mentions the guardrail, but that is prose — minimal edit is fine.

**Step 4: Run tests to verify they pass**

Run: `cd team-pulse-lib && uv run pytest -q`
Expected: PASS (full library suite).

**Step 5: Lint + commit**

Use `python_check` on `team-pulse-lib/team_pulse_lib/`.
Expected: no errors.

`cd team-pulse-lib && git add team_pulse_lib/errors.py team_pulse_lib/__init__.py tests/test_public_surface.py && git commit -m "refactor(lib): delete TeamPulseUnsupportedError and its exports"`

---

### Task 12: Remove `source_session_ids` field entirely from `AnswerUpload`

**Why:** The transitional default (Task 1) has done its job — no caller anywhere passes `source_session_ids`. Remove the field for real.

**Files:**
- Modify: `team-pulse-lib/team_pulse_lib/models.py` (delete the `source_session_ids` field)
- Modify: `team-pulse-lib/tests/test_models.py` (replace the transitional test with a "field is gone" assertion)

**Step 1: Write the failing test**

In `team-pulse-lib/tests/test_models.py`, **replace** the transitional test `test_source_session_ids_is_optional_transitional` (added in Task 1) with:

```python
    def test_source_session_ids_field_is_gone(self) -> None:
        field_names = {f.name for f in dataclasses.fields(AnswerUpload)}
        assert "source_session_ids" not in field_names

    def test_construct_without_sessions_uses_metadata(self) -> None:
        a = AnswerUpload(
            question_id="q1",
            user_id="u1",
            answer="text",
            generated_at="2026-06-25T17:00:00Z",
            metadata={"source_session_ids": ["s1"]},
        )
        assert a.metadata == {"source_session_ids": ["s1"]}
```

**Step 2: Run test to verify it fails**

Run: `cd team-pulse-lib && uv run pytest tests/test_models.py::TestAnswerUpload::test_source_session_ids_field_is_gone -v`
Expected: FAIL — the field is still present.

**Step 3: Remove the field**

In `team-pulse-lib/team_pulse_lib/models.py`, delete the `source_session_ids` line so `AnswerUpload` becomes exactly:

```python
@dataclass
class AnswerUpload:
    """Payload sent to the server when submitting an AI-synthesised answer."""

    question_id: str
    user_id: str
    answer: str
    generated_at: str  # ISO-8601 UTC string, e.g. "2026-06-25T17:00:00Z"
    metadata: dict[str, Any] = field(default_factory=dict)
```

**Step 4: Run tests to verify they pass**

Run: `cd team-pulse-lib && uv run pytest -q`
Expected: PASS (full library suite).

Then confirm the shim still passes against the editable lib (it constructs `AnswerUpload` without `source_session_ids` after Task 9):

Run: `cd modules/tool-team-pulse && uv run pytest -q`
Expected: PASS.

**Step 5: Commit**

`cd team-pulse-lib && git add team_pulse_lib/models.py tests/test_models.py && git commit -m "feat(lib): remove source_session_ids from AnswerUpload (lives in metadata now)"`

---

### Task 13: Update `context/using-team-pulse.md`

**Why:** The bundle doc still documents `source_session_ids` as a top-level submit parameter and shows it in the worked example. Move it inside `metadata`, and drop the stale `source` reference in the response-shape note.

**Files:**
- Modify: `context/using-team-pulse.md` (the "Submitting an answer" section, ~lines 229-290)

**Step 1: Update the parameter table**

In `context/using-team-pulse.md`, in the `team_pulse_submit_answer` **Parameters** table (lines 236-242), **remove** the `source_session_ids` row and **add** a `metadata` row:

```markdown
| Parameter | Required | Notes |
|---|---|---|
| `question_id` | yes | **Bare slug** — e.g. `higher-level-work`, NOT `questions/higher-level-work`. Strip the `questions/` prefix if you have it from a resource lookup. |
| `user_id` | yes | GitHub username of the person the answer is about (e.g. `jdoe`). The bundle records it as a github-namespaced identity (`respondent: {provider: "github", id: <user_id>}`), stored **verbatim** — resolution to a team member happens at read time. |
| `answer` | yes | The answer body. Min length 1. |
| `generated_at` | yes | ISO-8601 timestamp when the answer was generated (e.g. `2026-05-31T02:15:30.000+00:00`). |
| `metadata` | no | Opaque bag stored **verbatim** by the server. **Session provenance lives here**: pass `source_session_ids` (array of Context Intelligence session IDs) inside `metadata`. May also carry timing, model, confidence, etc. Omit for a bare submit. |
```

**Step 2: Update the worked example**

**Replace** the worked-example code block (lines 265-286) with:

```python
# 1. List all active questions to find the right slug
questions = team_pulse_resources(type="question")
# result.resources: [{id: "questions/higher-level-work", title: "...", ...}, ...]

# 2. The list envelope uses hierarchical IDs — strip the prefix
question_id = "higher-level-work"  # NOT "questions/higher-level-work"

# 3. Submit the answer — session provenance goes INSIDE metadata
result = team_pulse_submit_answer(
    question_id=question_id,
    user_id="jdoe",                   # github username of the analyzed person
    answer="Based on recent session analysis, ...",
    generated_at="2026-05-31T02:15:30.000+00:00",
    metadata={
        "source_session_ids": [
            "846491a9-8082-4e0c-95f9-32b90a3d15a0",
            "fe291191-419d-4a97-b42b-d76e6193c5e7",
        ],
    },
)
# On success: result.output is the persisted record envelope
# On failure: result.error.{code, message, status}
```

Then update the trailing note (lines 288-290): drop the `respondent_handle`/`source` specifics and say the server returns the persisted record on `201`; metadata is echoed back verbatim with session provenance inside it.

**Step 3: Verify no stale references remain**

Run: `grep -n "source_session_ids" context/using-team-pulse.md`
Expected: every remaining hit is **inside** a `metadata` example (no top-level parameter usage).

Run: `grep -n "guardrail\|capability\|server_supports_metadata\|TeamPulseUnsupportedError" context/using-team-pulse.md`
Expected: no matches.

**Step 4: Commit**

`git add context/using-team-pulse.md && git commit -m "docs: document answer metadata bag; move source_session_ids inside metadata"`

---

### Task 14: Final gate — full lib + shim suites + `python_check`

**Why:** Prove the whole change is green end-to-end across both packages before handing back.

**Files:** none (verification only).

**Step 1: Run the full library suite**

Run: `cd team-pulse-lib && uv run pytest -q`
Expected: PASS, zero failures. No `capability`/`guardrail` tests collected (deleted). No `source_session_ids` or `server_supports_metadata` references.

**Step 2: Run the full shim suite**

Run: `cd modules/tool-team-pulse && uv run pytest -q`
Expected: PASS, zero failures.

**Step 3: Confirm the zero-amplifier-dependency invariant still holds**

Run: `cd team-pulse-lib && uv run pytest tests/test_no_amplifier_import.py tests/test_no_amplifier_imports.py -q`
Expected: PASS — the library remains free of any `amplifier_*` import (CI-guarded).

**Step 4: Lint + types across both packages**

Use `python_check` on:
- `team-pulse-lib/team_pulse_lib/`
- `team-pulse-lib/examples/`
- `team-pulse-lib/tests/`
- `modules/tool-team-pulse/amplifier_module_tool_team_pulse/`
- `modules/tool-team-pulse/tests/`

Expected: `success: true` (no errors; warnings OK).

**Step 5: Final sweep — confirm the deleted subsystem is truly gone**

Run from repo root:

```
grep -rn "TeamPulseUnsupportedError\|server_supports_metadata\|source_session_ids\|parse_capabilities\|CapabilityCache\|_enforce_capability_guardrail" \
  team-pulse-lib/team_pulse_lib team-pulse-lib/examples team-pulse-lib/tests \
  modules/tool-team-pulse/amplifier_module_tool_team_pulse modules/tool-team-pulse/tests \
  context/using-team-pulse.md
```

Expected: the ONLY remaining hits are `source_session_ids` appearing **as a key inside a `metadata` dict** (in examples, the shim schema description, a couple of tests, and the doc's metadata example). Zero hits for `TeamPulseUnsupportedError`, `server_supports_metadata`, `parse_capabilities`, `CapabilityCache`, `_enforce_capability_guardrail`, and `capability.py` is gone.

**Step 6: Confirm clean git state**

Run: `git -C team-pulse-lib status --short && git -C modules/tool-team-pulse status --short`
(If both packages share the bundle repo's single git, run `git status --short` at repo root.)
Expected: all changes committed; no stray modified/untracked source files.

**Step 7: Stop**

Do NOT push, open a PR, or deploy. Report completion. Remember the release of this change waits on the server-first deploy (see Sequencing note).

---

## Appendix — verification cheat-sheet

| Invariant | How to check |
|---|---|
| Wire body is exactly the 5 partner keys, `metadata` always present | `tests/test_api_methods.py::test_upload_answer_sends_exact_partner_wire_body_on_201` |
| `metadata == {}` sent on bare submit | same test asserts `body["metadata"] == {}` |
| `source_session_ids` field gone from `AnswerUpload` | `tests/test_models.py::TestAnswerUpload::test_source_session_ids_field_is_gone` |
| `server_supports_metadata` gone from `ClientInfo` | `tests/test_models.py::TestClientInfo::test_server_supports_metadata_field_is_gone` |
| `TeamPulseUnsupportedError` not exported | `tests/test_public_surface.py::test_unsupported_error_is_gone` |
| `capability.py` deleted | file absent; `grep` finds no `parse_capabilities`/`CapabilityCache` |
| Shim submit schema drops `source_session_ids`, adds optional `metadata` | `tests/test_submit_answer_shim.py::test_schema_has_no_source_session_ids` + `test_schema_allows_optional_metadata` |
| Shim status output drops `server_supports_metadata` | `tests/test_status.py::test_status_output_has_no_server_supports_metadata` |
| Lib stays amplifier-free | `tests/test_no_amplifier_import*.py` |
| Sessions now live in metadata (shim) | `tests/test_submit_answer_shim.py::test_answer_upload_carries_all_input_fields` |
