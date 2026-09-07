# Per-description sizes, before -> after

`desc` = the `description` string alone. `rendered` = the full provider-facing
payload (name + description + input_schema JSON) as read out of a live mounted
session. Parameter descriptions inside `input_schema` were NOT touched.

| Tool | desc before | desc after | Δ | rendered before | rendered after | Δ | status |
|---|---:|---:|---:|---:|---:|---:|---|
| `team_pulse_ask` | 494 | 425 | -69 | 838 | 769 | -69 | leaned |
| `team_pulse_configure` | 747 | 616 | -131 | 1131 | 1000 | -131 | leaned, over cap (named contract) |
| `team_pulse_download_corpus` | 788 | 705 | -83 | 1308 | 1225 | -83 | leaned, over cap (named contract) |
| `team_pulse_get` | 296 | 296 | +0 | 519 | 519 | +0 | preserved byte-for-byte |
| `team_pulse_graph` | 314 | 288 | -26 | 436 | 410 | -26 | leaned |
| `team_pulse_info` | 448 | 325 | -123 | 569 | 446 | -123 | leaned |
| `team_pulse_prefix` | 181 | 181 | +0 | 409 | 409 | +0 | preserved byte-for-byte |
| `team_pulse_resources` | 567 | 441 | -126 | 1269 | 1143 | -126 | leaned |
| `team_pulse_search` | 232 | 232 | +0 | 640 | 640 | +0 | preserved byte-for-byte |
| `team_pulse_status` | 783 | 688 | -95 | 906 | 811 | -95 | leaned, over cap (named contract) |
| `team_pulse_submit_answer` | 870 | 789 | -81 | 1745 | 1662 | -83 | leaned, over cap (named contract) |
| `team_pulse_whoami` | 424 | 382 | -42 | 547 | 505 | -42 | leaned |
| **TOTAL** | **6144** | **5368** | **-776** | **10317** | **9539** | **-778** | |

Descriptions: 6144 -> 5368 chars (-12.6%).
Rendered team-pulse tool surface: 10317 -> 9539 chars (-7.5%).

In-description `<example>` blocks: 0 -> 0.  `<commentary>` blocks: 0 -> 0.
