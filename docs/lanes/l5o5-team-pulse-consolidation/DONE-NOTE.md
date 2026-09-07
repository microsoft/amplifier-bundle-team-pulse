# l5o5 — team-pulse consolidation, 12 tools → 3

**Outcome: A (RESOLVED).** Every deliverable is DONE. Nothing was recorded
NOT-POSSIBLE. Spend: **$0.00** against a $0.00 authority — text edits, local test
runs, and two live-mount renders, no API measurement.

**PR: https://github.com/microsoft/amplifier-bundle-team-pulse/pull/42**

**MERGE WAITS FOR THE BUNDLE OWNER'S ACK.** This lane did not merge and will not.
Beyond the standing never-merge rule, this specific item additionally requires
`samueljklee`'s explicit ack recorded in HIGHWAY.md before the manager merges —
CI-green is necessary here, not sufficient. 9 real users; not the owner's own tool.

---

## Deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | Exactly 3 `team_pulse_*` tools mounted | **DONE** — `team_pulse_read`, `team_pulse_write`, `team_pulse_ask` |
| 2 | Fail-before test: count == 3, and all 9 used names resolve via the compat table | **DONE** — `evidence/fail-before.txt` |
| 3 | Rendered surface before/after, scratch home, owner settings untouched, md5-verified | **DONE** — 9,967 → 3,954 (target ≤ 4,000) |
| 4 | PR body quotes the usage table verbatim + the byte delta | **DONE** — PR #42 |
| 5 | PR opened DRAFT, comment tags `samueljklee`, marked READY after re-verification | **DONE** |
| 6 | Compatibility table in the module, 9-with-calls → exactly one (tool, op) each | **DONE** — `COMPAT_TABLE`, all 12 names |
| 7 | Merge waits for owner ack | **HELD OPEN, by design** |
| 8 | Anything already compliant left unedited and named | **DONE** — see "Left unedited" |

## What shipped

Three mounted tools:

- `team_pulse_read(op: get | search | prefix | resources | graph | info | whoami | status)`
- `team_pulse_write(op: submit_answer | download_corpus | configure)`
- `team_pulse_ask` — **byte-identical** to before. It triggers server-side LLM spend,
  so it stays an explicit, undisguised call and is never an op behind an enum.
  (494 description chars / 812 rendered, before and after.)

The 11 per-op classes are retained as internal op handlers with their existing
request/response logic and tests — no longer mounted, so their descriptions no longer
reach a model. `COMPAT_TABLE` (public, importable) maps all 12 former names to exactly
one `(tool, op)` pair each.

Commits: `0d38813` (code + tests), `d47d4e7` (docs), plus the evidence commit.

## The number

Measured on a **live mounted session**, not counted from source: a scratch
`AMPLIFIER_HOME` built from a deep copy of the owner's 20-entry `bundle.app` list with
the team-pulse entry swapped for this checkout.

| metric | before (875c288) | after | delta |
|---|---:|---:|---:|
| tools mounted | 12 | 3 | −9 |
| description chars | 6,144 | 1,563 | −4,581 (−74.6%) |
| **rendered chars** | **9,967** | **3,954** | **−6,013 (−60.3%)** |

Total session tools 86 → 77 — exactly −9, which is the independent check that nothing
outside this bundle moved between the two runs.

`tests/test_consolidated_surface.py::test_rendered_surface_is_within_budget` recomputes
the same formula against `mount()` and fails above 4,000, so the surface cannot
silently regrow.

## Fail-before, recorded

Against `main`'s module (`evidence/fail-before.txt`): `mount()` registers **12** tools
(`assert len == 3 -> FAIL (got 12)`), and the new test errors at import on the missing
`COMPAT_TABLE`. Both are captured verbatim.

## Finding the goal did not anticipate: `main` was already red

`main` fails **4 tests** today, before this branch (`evidence/baseline-pytest.txt`).
All four are stale expectations that lagged behind shipped code:

1. `test_all_contains_exactly_11_tool_classes_and_mount` — asserted 11 classes against
   a module already exporting 12.
2. `test_all_has_exactly_12_names` — same drift.
3. `test_all_expected_names_present_including_status` — its expected set omitted
   `team_pulse_download_corpus` while `mount()` mounted it.
4. `test_resources_forwards_type_and_collection` — asserted `resources(type, collection)`
   against code that has passed `status=` since the question-lifecycle filter landed.

"Full test suite must stay green" was therefore unsatisfiable as written — it was not
green to begin with. All four are corrected here and the reason is stated in each test's
docstring. Suite: **4 failed / 72 passed → 103 passed** (plus **209 passed** in
`team-pulse-lib`, untouched and green throughout).

The PR offers to split that fix into its own PR if the owner prefers.

## Disclosure: the owner's settings.yaml md5 changed mid-run — not this lane

md5 `46626a41…` at T0 and immediately after the scratch home was built; `028a195c…`
observed after the AFTER render. **This lane never opened that file for writing.** A
concurrent sibling lane on the same machine did — the AFTER render's own log names
another lane's scratch home (`/tmp/hd-android-scratch-before-bfKCxP/…`) in an
editable-install `.pth`.

The measurement is unaffected: both renders read the same scratch settings.yaml,
written once at T0, and neither re-read the owner's file. The owner's file is intact —
still 20 app entries, still carrying the team-pulse git entry. Full log in
`evidence/owner-settings-md5.txt`.

## Left unedited, deliberately

- **`team_pulse_ask`** — description and schema byte-identical. Not consolidated, on
  purpose.
- **`docs/plans/2026-06-26-team-pulse-lib-alignment-implementation.md`** (73 old-name
  refs) — a dated record of an earlier implementation, not live guidance. Rewriting it
  would falsify a historical document.
- **`team-pulse-lib/examples/README.md`** — its one `team_pulse_server` match is a
  pytest fixture, not a tool.
- **`team_pulse_lib`** everywhere — the Python package name, not a tool name.
- **The whole `team-pulse-lib/` package** apart from its README's tool-mapping table —
  the consolidation is an Amplifier-adapter concern; the client library needed no change.

## Honest limits

- The 9,967 "before" figure is this lane's formula. The `hd-team-pulse` lane measured
  10,317 and the goal quotes ~10,624 for the *same 12 tools* — three serializations of
  the same schema JSON. The **delta** is apples-to-apples (one formula, one machine,
  two runs); the absolute number is only comparable to a figure produced the same way.
- The two new descriptions are a judgment call about what an agent needs in-schema
  versus what belongs in the mode-gated reference doc. The 4,000-char target was met at
  3,954 — 46 chars of headroom, so any future addition to either description has to buy
  its place.
- No live call against a real team-pulse endpoint was made ($0 authority). Routing is
  verified against mocked clients, which is what the pre-existing suite does too.
