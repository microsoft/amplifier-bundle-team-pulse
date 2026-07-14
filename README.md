# amplifier-bundle-team-pulse

An [Amplifier](https://github.com/microsoft/amplifier) bundle that wraps the
**team-pulse lens API** — a read-only HTTP surface over the team's structured
vault of people, projects, initiatives, outcomes, tasks, and design docs.

Gives an Amplifier session three things:

| Component | What it is | How you use it |
|---|---|---|
| **Tools** (`team_pulse_*`) | Six tool-callable wrappers over the lens API endpoints | Always available when the bundle is loaded |
| **Mode** (`/team-pulse`) | A context overlay that biases the assistant toward consulting team-pulse first | Activate with `/mode team-pulse` |
| **Agent** (`team-pulse-expert`) | A read-only lookup specialist that knows the data model + endpoint patterns | Contributed by `/team-pulse` mode — available for delegation **while the mode is active** |

## Activation model

The bundle is split between always-on machinery (the tools) and mode-gated
context (the agent + reference doc):

| Piece | When loaded | Per-session cost when `/team-pulse` is off |
|---|---|---|
| Six `team_pulse_*` tools | Always (when bundle is included) | ~1K tokens of tool schemas in system prompt |
| `team-pulse-expert` agent | Only while `/team-pulse` mode is active | **0 tokens** — not in the delegate catalog |
| `context/using-team-pulse.md` reference doc | Only while `/team-pulse` mode is active | **0 tokens** — not injected |

To get the full team-pulse experience (agent + reference doc available),
activate the mode first:

```
> /mode team-pulse
> who's working on the onboarding initiative?
```

With the mode off, you can still call the `team_pulse_*` tools directly,
but the assistant won't have the agent or the data-model reference loaded
— it'll have to figure things out from tool descriptions alone.

> **v1 limitation (1/2): `contributes.tools` deferred.** The tools stay
> always-on because `contributes.tools` is deferred to Amplifier mode-system
> v1.1. When that lands, the tools will become mode-gated too and the whole
> bundle will be zero-cost when off.
>
> **v1 limitation (2/2): `contributes.agents.<name>.source` not resolved.**
> The expected ergonomic form for mode-gated agents is a one-line
> `source: "@team-pulse:agents/team-pulse-expert"` reference. In v1 the
> contributions overlay never resolves that into the full agent dict the
> spawner expects, so the agent ends up in the delegate catalog as
> "No description" and spawns as a copy of the parent. As a workaround the
> agent definition is **inlined** into `modes/team-pulse.md`'s
> `contributes.agents` block ({description, instruction, model_role} — the
> same shape the always-on agent loader produces). The cost model is
> unaffected. See the long comment in `modes/team-pulse.md` for details and
> rollback notes. (TODO: file upstream issue.)

## Quick start

### 1. Add the bundle to your Amplifier app

#### Option A — Behavior install, recommended for existing setups (layers cleanly, no extra dependencies)

If you already have an active bundle or a configured `~/.amplifier/settings.yaml`, install just
the behavior. This layers team-pulse on top of your existing setup without pulling in
foundation or modes as extra dependencies:

```bash
amplifier bundle add --app git+https://github.com/microsoft/amplifier-bundle-team-pulse@main#subdirectory=behaviors/team-pulse.yaml
```

Or add it manually to `~/.amplifier/settings.yaml`:

```yaml
bundle:
  app:
    - git+https://github.com/microsoft/amplifier-bundle-team-pulse@main#subdirectory=behaviors/team-pulse.yaml
```

#### Option B — Full standalone bundle (brings foundation + modes)

Use this if you want a self-contained setup from scratch and are happy to have foundation
and the modes bundle pulled in as dependencies:

```bash
amplifier bundle add --app git+https://github.com/microsoft/amplifier-bundle-team-pulse@main
```

#### Option C — Compose into a parent bundle

If you maintain your own bundle.md, reference the behavior from its `includes`:

```yaml
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-team-pulse@main#subdirectory=behaviors/team-pulse.yaml
```

Or include the full root bundle if you want to pull in the complete standalone stack:

```yaml
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-team-pulse@main
```

### 2. Mint a key

Go to your team-pulse admin UI (the deployment owner can point you to it —
typically `<lens-api-url>/admin` → **"API keys"** panel) and mint a
personal key. Keys look like `tp_…` and are scoped to read-only API
access. The raw key is shown **once** at mint time — save it immediately.

### 3. Configure your key

The `key` must always be supplied, and the `url` must also be set — the bundle
ships no default endpoint (see **Set the URL** below). There are two ways to
provide the key.

#### Option A — `~/.amplifier/settings.yaml` (recommended for daily use)

```yaml
overrides:
  tool-team-pulse:
    config:
      key: "tp_yourkeyhere"
```

A paste-ready version of this block lives at
[`examples/settings.snippet.yaml`](examples/settings.snippet.yaml).

#### Option B — Environment variables (good for CI / scripted setups)

```bash
export AMPLIFIER_TEAM_PULSE_KEY=tp_yourkeyhere
```

#### Set the URL (required)

The bundle ships no default endpoint, so you must set the lens API URL to your
team-pulse deployment, either in settings:

```yaml
# ~/.amplifier/settings.yaml
overrides:
  tool-team-pulse:
    config:
      url: "https://team-pulse.staging.example.com"
```

or via env var:

```bash
export AMPLIFIER_TEAM_PULSE_URL=https://team-pulse.staging.example.com
```

#### Precedence

For each field: **settings.yaml (non-empty) → env var → bundle default
(URL only) → fail.** If neither source provides a value, `mount()` raises
a `ValueError` that names BOTH paths so you know where to fix it — better
than silent 401s on every call. An empty string in settings counts as
"not set" so a YAML placeholder can't shadow your env-var setup.

### 4. Verify

Start an Amplifier session that loads this bundle and ask a factual
question:

```
> what's the team-pulse project?
```

The recommended starting move is to activate the mode first — that mounts
the expert agent and reference doc, so delegation works:

```
> /mode team-pulse
> what's the team-pulse project?
> list all projects
```

The assistant should delegate to `team-pulse-expert`, which fetches
`projects/team-pulse` from the lens API and surfaces the result. Without
the mode active you can still call `team_pulse_*` tools directly, but the
expert agent won't be available for delegation.

## What the agent will (and won't) do

The `team-pulse-expert` agent is deliberately scoped to **read-only
factual lookup** in v1. It will:

* Fetch a specific resource (`team_pulse_get`)
* List resources of a type (`team_pulse_resources`)
* Search fuzzily (`team_pulse_search`)
* Walk the graph for cross-resource relationships (`team_pulse_graph`)
* Surface API errors verbatim (preserves the lens API's `{code, message, status}` envelope)

It will NOT:

* Score project health, risk, or velocity
* Recommend what someone should be working on
* Invent fields the lens API doesn't return
* Mutate anything (the lens API is read-only)

A "thinking partner" agent that reasons over the data is on the roadmap.
It's deferred to v2 to keep v1 honest: the boundary between "fetch facts"
and "make judgments" is genuinely useful for the caller.

## Architecture

A thin standalone bundle composing foundation + the modes system + this
bundle's behavior:

```
bundle.md                       # standalone — composes foundation, modes, behavior
behaviors/team-pulse.yaml       # wires the tool module ONLY (agent + context are mode-gated)
context/using-team-pulse.md     # data model + endpoint reference (loaded by mode + by spawned agent)
modes/team-pulse.md             # /team-pulse mode — contributes the inlined agent + reference doc
modules/tool-team-pulse/        # Python module: client + tools
```

> **v1 packaging note.** In a v1.1-or-later world the expert agent would live in
> its own `agents/team-pulse-expert.md` file and be referenced from the mode as
> `source: "@team-pulse:agents/team-pulse-expert"`. In v1 that `source:`
> reference is not resolved by the contributions overlay (it never calls the
> agent-file metadata loader), so the agent definition is inlined into
> `modes/team-pulse.md`'s `contributes.agents` block. The inline shape matches
> what the always-on agent loader would have produced — `description`,
> `instruction`, `model_role`. See the comment block in the mode file for
> details and rollback notes.

**Context strategy** — zero always-on context. The agent and reference doc
are mode-gated via `modes/team-pulse.md`'s `contributes` block — they only
mount when `/team-pulse` is active. The agent's body also @-mentions the
reference doc, so once the agent spawns into a child session it has the
data-model reference available regardless of mode state. Sessions that
never activate the mode and never delegate to the expert pay nothing for
team-pulse context — only the ~1K tokens of tool schemas.

## The lens API

| Endpoint | Tool | Notes |
|---|---|---|
| `GET /api/lens/info` | `team_pulse_info` | Self-doc — resource types, capabilities, endpoint catalog |
| `GET /api/lens/resources` | `team_pulse_resources` | List, optional `type` filter, `view` = `effective` or `raw` |
| `GET /api/lens/resources/search` | `team_pulse_search` | Naive text search, default limit 50, max 200 |
| `GET /api/lens/resources/prefix/{p}` | `team_pulse_prefix` | Hierarchical ID listing |
| `GET /api/lens/resources/{id}` | `team_pulse_get` | Fetch one resource |
| `GET /api/lens/graph` | `team_pulse_graph` | Full composed entity graph + reverse edges — **large** |

Resource types: `team`, `outcomes`, `initiative`, `project`, `member`,
`task`, `doc`. Single-resource envelope: `{id, title, type, data,
metadata}` for entities, or `{id, title, type, content, metadata}` for
docs — switch on `type`. List envelope: `{resources: [{id, title, type}],
count}`. Error envelope: `{error: {code, message, status}}`.

The six tools above work generically over every resource type, including
`doc`. `doc` IDs are hierarchical paths like
`docs/handbook/onboarding/onboarding.md` and surface the team-pulse vault's
markdown design docs. Doc bodies come back as raw markdown in the
`content` field; entity bodies remain in the structured `data` dict.

## Development

```bash
cd modules/tool-team-pulse
uv venv
uv pip install -e ".[dev]"
uv run pytest
```

20 unit tests cover the client + error-envelope translation + the
mount-time config resolution (settings → env-var fallback). The tests
use `respx` to mock the HTTP layer; no live API calls required.

## License

MIT. See `LICENSE`.

## Contributing

Most contributions require you to agree to a Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or logos are subject to those third-parties' policies.

## Code of Conduct

This project has adopted the Microsoft Open Source Code of Conduct. For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.
