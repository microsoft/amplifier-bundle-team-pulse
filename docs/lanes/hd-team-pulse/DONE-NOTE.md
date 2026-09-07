# Lane hd-team-pulse — lean the team-pulse head surface without semantic loss

Work item: `model_performance-bceb` — *Lean head: team-pulse 12 tool descriptions plus awareness*.

Draft PR: <https://github.com/microsoft/amplifier-bundle-team-pulse/pull/41> (**do not merge**).
Discovered work filed: `model_performance-q10g` (4 stale tests failing on main, pre-existing).

## What this changes

The 12 `team_pulse_*` tool descriptions are always-on context: every one is
rendered into the system prompt of every session that loads this bundle, whether
or not team-pulse is ever called. Nine were rewritten trigger-first and tightened;
three were already trigger-first and tight and are preserved **byte-for-byte**.
No parameter description, no schema, and no runtime behaviour was touched.

- `modules/tool-team-pulse/amplifier_module_tool_team_pulse/tool.py` — 9 `description` strings.
- `modules/tool-team-pulse/tests/test_description_surface.py` — **new**: byte pins,
  the semantic-fidelity inventory as an executable check, and the shape rules.

## Headline numbers

| | before | after | Δ |
|---|---:|---:|---:|
| 12 `description` strings | 6,144 | 5,368 | **−776 (−12.6%)** |
| Rendered team-pulse tool surface | 10,317 | 9,539 | **−778 (−7.5%)** |
| Semantics carried | 123 | 123 | **0 lost** |
| In-description `<example>` blocks | 0 | 0 | — |
| In-description `<commentary>` blocks | 0 | 0 | — |
| Descriptions preserved byte-for-byte | — | 3 | — |

Per-description sizes: [`evidence/sizes-before-after.md`](evidence/sizes-before-after.md).

| Tool | desc before | desc after | Δ | status |
|---|---:|---:|---:|---|
| `team_pulse_ask` | 494 | 425 | −69 | leaned |
| `team_pulse_configure` | 747 | 616 | −131 | leaned, over cap (named contract) |
| `team_pulse_download_corpus` | 788 | 705 | −83 | leaned, over cap (named contract) |
| `team_pulse_get` | 296 | 296 | +0 | **preserved byte-for-byte** |
| `team_pulse_graph` | 314 | 288 | −26 | leaned |
| `team_pulse_info` | 448 | 325 | −123 | leaned |
| `team_pulse_prefix` | 181 | 181 | +0 | **preserved byte-for-byte** |
| `team_pulse_resources` | 567 | 441 | −126 | leaned |
| `team_pulse_search` | 232 | 232 | +0 | **preserved byte-for-byte** |
| `team_pulse_status` | 783 | 688 | −95 | leaned, over cap (named contract) |
| `team_pulse_submit_answer` | 870 | 789 | −81 | leaned, over cap (named contract) |
| `team_pulse_whoami` | 424 | 382 | −42 | leaned |
| **TOTAL** | **6,144** | **5,368** | **−776** | |

## The honest finding: this surface was dense, not bloated

−12.6% is the real ceiling here, and that is the result, not a shortfall. These
descriptions were not padded with examples, preamble or restated schema; they were
already close-packed rules. Measured density before the change: `team_pulse_configure`
carried 14 distinct semantics in 747 chars (53 chars each) — *tighter per semantic*
than `team_pulse_prefix` (181 chars, 3 semantics, 60 each), the shortest description
in the set. The bytes were being spent on real constraints and failure modes, and the
brief forbids dropping any of them.

So the win is mostly **ordering, not volume**: nine descriptions now open with the
trigger — when to reach for the tool — instead of a definition, a mechanism, or a
caveat, with the same rules following. Two examples:

- `team_pulse_ask` used to open by defining what `ask` is and buried its one hard
  gate ("only when the user explicitly directs Team Pulse to answer") in the last
  sentence. That gate is now the first clause.
- `team_pulse_status` used to open with its response-field list and reveal its
  actual job — diagnosing auth/connection failures when nothing else works — three
  sentences later. Reversed.

Anyone hoping for a 40% cut should read the fidelity table first: the bytes are
load-bearing.

## Proof

### 1. Semantic fidelity — 123 semantics, 0 absent

[`evidence/fidelity-table.md`](evidence/fidelity-table.md) enumerates every
behaviour, constraint, parameter semantic and failure mode carried by the
**pre-lean** descriptions, one row at a time, and records whether it survives.

**Total semantics: 123. Present: 123. Absent: 0.**

The table is not hand-written prose — it is generated from
`SEMANTICS` in `test_description_surface.py`, where each row carries a probe that
must still match the current text. `test_no_semantic_is_absent` fails **by
semantic id** if one is dropped.

The check was verified non-vacuous by mutation: deleting the "shared API key is
refused (403) … must be attributable to a member" clause from
`team_pulse_download_corpus` made the suite fail naming `DL-13` and `DL-14`, and
restoring it made it pass again.

### 2. Byte pins

`test_description_bytes_are_pinned` pins the SHA-256 of all 12 descriptions, so no
description can drift in either direction without a deliberate re-pin.

`test_already_compliant_descriptions_are_preserved_byte_for_byte` pins the three
untouched ones separately, against their **pre-change** bytes — verified equal to
`git show HEAD:` for `team_pulse_get`, `team_pulse_prefix` and `team_pulse_search`.
"Preserved byte-for-byte" is machine-checked, not asserted.

### 3. Shape rules

- `test_no_example_or_commentary_blocks` — 0 `<example>` / `<commentary>` in all 12,
  before and after. They belong in agent definitions, never in an always-on tool
  description.
- `test_length_cap` — ≤ 600 chars, except four descriptions that carry a **named**
  parameter (or named response-field) contract the JSON schema alone does not
  express. Each exemption names the contract that earns it, and the test *fails* if
  an exempt description drops under the cap, so a stale exemption cannot linger:
  - `team_pulse_submit_answer` (789) — `question_id` / `user_id` / `generated_at` / `metadata`
  - `team_pulse_download_corpus` (705) — `dest_dir` / `folder` + the bearer-only auth rule
  - `team_pulse_status` (688) — the exact response field list it promises
  - `team_pulse_configure` (616) — `client_id` + `AMPLIFIER_TEAM_PULSE_KEY` precedence
- `test_first_sentence_is_the_trigger` — no description opens with a caveat marker.

### 4. Rendered tool surface, before → after

Method and commands: [`evidence/rendered-surface-method.md`](evidence/rendered-surface-method.md).
Raw dumps: [`rendered-surface-before.json`](evidence/rendered-surface-before.json),
[`rendered-surface-after.json`](evidence/rendered-surface-after.json).

Measured from a **fresh scratch `AMPLIFIER_HOME`** (`/tmp/hdtp/amp-home`) whose
settings were built from a **deep copy** of the owner's `bundle.app` list — the
owner's `~/.amplifier/settings.yaml` was read only, never moved or edited (md5
identical before and after), and the owner's cache was never written to. The single
`team-pulse` git entry was repointed at this checkout so the edits under test are
what mounts; the other 19 entries are unchanged. 20 app entries in, 20 out; 86 tools
mounted, 12 of them `team_pulse_*`.

Team-pulse rendered surface (name + description + `input_schema`):
**10,317 → 9,539 chars (−778, −7.5%)**, against an 86-tool session total of 187,202.

`amplifier tool info` was tried first and rejected — it prints mount metadata and
never the description, so it cannot measure this. `render_surface.py` (checked in
under `evidence/`) mirrors the CLI's own mount path and dumps the full
provider-facing payload.

**On the goal's 10,624-char figure:** that is the *rendered* surface, not the
descriptions alone. Measured here: descriptions 6,144, rendered 10,317 — the ~300
gap is serialization whitespace. Both numbers are reported so neither reading is
ambiguous.

### 5. `validate-agents` — PASS

[`evidence/validate-agents.txt`](evidence/validate-agents.txt).

Structural summary: `total=0 errors=0 warnings=0`. No agent-definition defects.

Two things stated plainly rather than glossed:

1. **Only the deterministic phases were run.** This lane's budget is $0 / no API
   calls; the recipe's `quality-classification`, `description-quality-check`,
   `tool-access-analysis` and `synthesize-report` steps are LLM-backed. The three
   pure-Python phases (`environment-check`, `agent-discovery`,
   `structural-validation`) were extracted from
   `@foundation:recipes/validate-agents.yaml` v1.8.0 verbatim and run against this
   checkout. They are also the only phases a change to this repo could affect.
2. **Discovery finds zero agent files, and that is pre-existing.** This repo ships no
   `agents/*.md`: its one agent, `team-pulse-expert`, is *inlined* into
   `modes/team-pulse.md`'s `contributes.agents` block — a documented v1 workaround
   (see the comment block in that file and in `behaviors/team-pulse.yaml`). Discovery
   reports `no_agents` identically before and after; this change touches no agent
   file at all.

### 6. Tests

[`evidence/pytest.txt`](evidence/pytest.txt).

- New `test_description_surface.py`: **54 passed**.
- `team-pulse-lib/tests`: **209 passed**.
- `modules/tool-team-pulse/tests`: 126 passed, **4 failed — all four fail identically
  on the untouched baseline** (`git stash`, same command, same four). This change
  introduces zero new failures. The four are stale count/signature expectations,
  unrelated to descriptions:
  - `test_init_exports.py::test_all_has_exactly_12_names` — `__all__` has 13 entries
  - `test_init_exports.py::test_all_contains_exactly_11_tool_classes_and_mount`
  - `test_mount.py::test_all_expected_names_present_including_status` — extra `team_pulse_download_corpus`
  - `test_read_tools.py::test_resources_forwards_type_and_collection` — `resources()` now also forwards `status=`

  Filed as discovered work rather than fixed here, to keep this lane to its brief.

### 7. CI

**This repository has no CI.** `.github/` contains only `PULL_REQUEST_TEMPLATE.md` —
no `workflows/` directory, no pipeline of any kind. There is nothing to go green;
the pytest and `validate-agents` runs above are the whole verification story, and
they were run by hand.

## Scope decisions

**The awareness surface is not owned by this repo — nothing to lean.**
`behaviors/team-pulse.yaml` declares `context: include: []` with an explicit comment
("Intentionally empty: zero always-on context"). The reference docs
(`context/using-team-pulse.md`, `context/corpus-retrieval.md`) are mounted only by
`modes/team-pulse.md`'s `contributes.context`, i.e. only while `/team-pulse` mode is
active. The 12 tool descriptions are this bundle's *entire* always-on head.

**The mode-inlined agent description is measured and deliberately left alone.**
`modes/team-pulse.md` carries a `team-pulse-expert` description containing 5
`<example>` and 5 `<commentary>` blocks (~1.9K chars) — the one place in this repo
where the "no examples in descriptions" rule would bite. It is out of this lane's
scope on both counts: it is not one of the 12 tool descriptions, and it is
**mode-gated**, so it costs zero tokens unless `/team-pulse` is active (the bundle
docs put it at ~3K saved when off). Leaning it is a real, separate piece of work with
a different risk profile — it changes the delegate catalog — and folding it into a
lane that must not merge would be scope creep. Recorded here so it is not lost.

**Class docstrings were not touched.** Each tool class has a docstring that partly
mirrors its description. Docstrings are developer-facing, are never rendered into the
head, and had *already* drifted from the descriptions before this change (e.g.
`TeamPulseResourcesTool`'s docstring mentions retired entity types that the
description never did). Rewriting them is diff noise for zero head-surface effect.
The new test pins the descriptions only.

**Parameter descriptions inside `input_schema` were not touched** — 1,502 chars
across the 12, byte-identical before and after. The brief targets the descriptions;
touching schemas would put a second, riskier change in the same diff.

## Reproducing

```bash
uv venv /tmp/hdtp/venv --python 3.12
VIRTUAL_ENV=/tmp/hdtp/venv uv pip install -e ./team-pulse-lib -e ./modules/tool-team-pulse pytest pytest-asyncio respx
/tmp/hdtp/venv/bin/python -m pytest modules/tool-team-pulse/tests/test_description_surface.py -q
```

## Spend

**$0. No API calls were made.** All measurement is static or mount-time; the only
LLM-backed step in scope (`validate-agents`' quality phases) was deliberately not
run, and that is disclosed above rather than papered over.
