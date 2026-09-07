# Rendered team-pulse tool surface: before vs after

Method: `evidence/render_surface.py` run against a LIVE mounted Amplifier
session from a scratch `AMPLIFIER_HOME` (`/tmp/l5o5/amp-home`) whose
`settings.yaml` is a COPY of the owner's 20-entry `bundle.app` list with the
`team-pulse` git entry swapped for this working checkout. The owner's
`~/.amplifier/settings.yaml` was read only, never written (see
`owner-settings-md5.txt`). `rendered` = `len(name) + len(description) +
len(json.dumps(input_schema))` -- the payload a provider actually receives.

## BEFORE (origin/main, 875c288)

Total tools mounted in the session: **86**. team-pulse tools: **12**.

| tool | description chars | rendered chars |
|---|---:|---:|
| `team_pulse_ask` | 494 | 812 |
| `team_pulse_configure` | 747 | 1103 |
| `team_pulse_download_corpus` | 788 | 1280 |
| `team_pulse_get` | 296 | 486 |
| `team_pulse_graph` | 314 | 397 |
| `team_pulse_info` | 448 | 530 |
| `team_pulse_prefix` | 181 | 376 |
| `team_pulse_resources` | 567 | 1250 |
| `team_pulse_search` | 232 | 623 |
| `team_pulse_status` | 783 | 867 |
| `team_pulse_submit_answer` | 870 | 1735 |
| `team_pulse_whoami` | 424 | 508 |
| **TOTAL** | **6144** | **9967** |

## AFTER (this branch, d47d4e7)

Total tools mounted in the session: **77**. team-pulse tools: **3**.

| tool | description chars | rendered chars |
|---|---:|---:|
| `team_pulse_ask` | 494 | 812 |
| `team_pulse_read` | 536 | 1477 |
| `team_pulse_write` | 533 | 1665 |
| **TOTAL** | **1563** | **3954** |

## Delta

| metric | before | after | delta |
|---|---:|---:|---:|
| tools mounted | 12 | 3 | -9 |
| description chars | 6144 | 1563 | -4581 (-74.6%) |
| **rendered chars** | **9967** | **3954** | **-6013 (-60.3%)** |

Target was <= 4,000 rendered chars: **3954 — met**.

`team_pulse_ask` is byte-identical before and after (494 desc / 812 rendered):
it is deliberately NOT consolidated.

## Note on the goal's ~10,624 figure

This lane measures the before-state at **9967** rendered chars with the formula
above. A prior lane (`hd-team-pulse`) measured 10,317 for the same 12 tools
using its own serialization of `input_schema`, and the goal quotes ~10,624.
All three are the same 12 tools under different serializations of the schema
JSON. The before/after numbers in this file are produced by ONE formula on
ONE machine, so the delta is apples-to-apples; the absolute number is only
comparable to another figure produced the same way.
