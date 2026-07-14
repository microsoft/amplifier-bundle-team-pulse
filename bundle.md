---
bundle:
  name: team-pulse
  version: 0.4.1
  description: Lens API tools, mode, and expert agent — read-mostly with one write tool for session-mining answer submission.

includes:
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main
  # modes framework now comes transitively via the team-pulse behavior
  # (behaviors/team-pulse.yaml includes the modes BEHAVIOR), so it no longer
  # needs to be listed here.
  - bundle: team-pulse:behaviors/team-pulse
---

# Team Pulse Bundle

Provides read-only access to the **team-pulse lens API** — the HTTP surface
exposing a team's **content collections** (mined knowledge: conversation /
decision wikis and code / repo wikis) plus a small set of structured resources
(**members** and reflection **questions**). The current shape of the surface is
self-describing — the agent reads it from `team_pulse_info()`, never a hardcoded
list.

## What's wired in

| Component | Where it lives | When loaded |
|---|---|---|
| `tool-team-pulse` (seven `team_pulse_*` tools — six read-only wrappers over all 8 resource types, plus one write tool for answer submission) | `behaviors/team-pulse.yaml` | **Always-on** (~1K tokens) — `contributes.tools` is v1.1 |
| `team-pulse-expert` agent (definition **inlined** into the mode; knows the 8 resource types incl. `doc` and `question`) | Mounted by `modes/team-pulse.md` via `contributes.agents` | Only while `/team-pulse` mode is active (zero cost otherwise) |
| `context/using-team-pulse.md` reference doc | Mounted by `modes/team-pulse.md` via `contributes.context` | Only while `/team-pulse` mode is active (zero cost otherwise) |
| `/team-pulse` mode | `modes/team-pulse.md`, discovered via the modes bundle | Activate with `/mode team-pulse` |

This bundle composes the modes bundle so `/team-pulse` auto-registers and
its `contributes` block can mount the agent + reference doc on activation.
The recommended starting move when you want the full lookup experience is
`/mode team-pulse` — that pulls the expert agent and reference into context
in one step.

> **Known v1 limitation.** The mode's `contributes.agents` block does not
> resolve `source:` references into full agent definitions, so the
> `team-pulse-expert` agent is **inlined** into `modes/team-pulse.md` rather
> than living in its own `agents/team-pulse-expert.md` file. The cost model
> is unaffected (still ~3K tokens when the mode is active, zero when it's
> off). See the long comment block in `modes/team-pulse.md` for the failure
> mode, the inline shape, and the rollback plan. (TODO: file upstream issue
> on amplifier-foundation `contributes.agents` source resolution.)

## Configuration

Set both the lens API URL (your team-pulse deployment) and your API **key** — the bundle ships no default endpoint:

```yaml
# ~/.amplifier/settings.yaml
overrides:
  tool-team-pulse:
    config:
      url: "https://<your-team-pulse-endpoint>"
      key: "tp_yourkeyhere"
```

Or via env var:

```bash
export AMPLIFIER_TEAM_PULSE_URL=https://<your-team-pulse-endpoint>
export AMPLIFIER_TEAM_PULSE_KEY=tp_yourkeyhere
```

Mint a key at `<url>/admin` → "API keys" panel (shown once — save it). See `README.md` for the full walk-through including URL configuration and precedence rules.

## Scope (v1)

Read-mostly lookup with one write tool. The agent answers factual questions
sourced from the lens API. The single write tool (`team_pulse_submit_answer`)
records AI-generated answers to reflection questions on behalf of a specified
user — session-mining provenance, the sole mutation path. The bundle does NOT
theorize, recommend, score risk, or apply rubrics — that's deferred to a future
"thinking-partner" agent.
