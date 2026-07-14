# Using the team-pulse lens API

Reference doc for the `team-pulse-expert` agent and the `/team-pulse` mode.
Explains the data surface, the endpoint reference, and common query patterns.

For the deep mechanics of traversing a content collection (discover sub-corpora,
scope search, JOIN a decision to its implementation, cite freshness, avoid
full-reading big index files), see `corpus-retrieval.md` — that is the primary
skill and this doc points into it.

## Tool selection — read by default, `ask` only when explicitly invoked

There are two ways to answer a Team Pulse question. Use **one path per answer** — never both.

**Default — read the corpus and compose yourself.** For every Team Pulse question (what's the team doing, who owns what, how things relate, orient me to an area, what did we decide about X), use the read tools and write the answer yourself, with citations: `team_pulse_info` (discover collections/types) -> `team_pulse_search` (find the specific page/entity) -> `team_pulse_get` (read that one page/entity, full fidelity) -> `team_pulse_resources`/`team_pulse_prefix` (list/browse). You are the synthesizer.

**Exception — `team_pulse_ask` (server-side synthesis): explicit request only.** The rule (not a phrasebook): call `ask` only when the user **names Team Pulse as the answerer** — they are asking the service to answer, not asking you a question that happens to be about the team. Example: "ask Team Pulse how we're tracking on the migration." Phrasing varies; the signal is **who they are asking**.

A synthesis-flavored question with **no** such request ("what's the overall status?", "summarize how the team's doing") is answered **from the corpus**, not by `ask`. `ask` never fires on your own initiative.

**One path per answer.** Either read-and-compose, or `ask` — not both in the same response.

## What team-pulse is

A small read-only HTTP service exposing a team's current knowledge over a lens
API. The bulk of that knowledge lives in **content collections** — a corpus
mined for the team (conversation / decision wikis, code / repo wikis). Alongside
the corpus, the lens serves a small set of **structured resources**: the team's
**members** and the admin's active reflection **questions**. When a question is
about the team's work — what shipped, who owns something, what was decided, how
to do something the team has done before — **the corpus is where you look.**

**The surface is self-describing — read it, don't recall it.** Call
`team_pulse_info()` first to learn the *live* set of resource types and content
collections. Do not answer "what data does Team Pulse have?" from this document
or from memory — the answer is whatever `/info` returns right now, and it changes
as the team's data evolves. Never hardcode a type or collection name.

### The current surface (read it from `/info`, don't assume it)

`team_pulse_info()` returns the authoritative shape. Today it typically returns:

| Kind | What it is | How to reach it |
|---|---|---|
| Content collections | The corpus (one or more sub-corpora — e.g. conversation/decision wikis and code/repo wikis). The primary current-knowledge surface. | `search`/`resources`/`prefix`/`get` scoped with `collection=<name>` — names from `/info`. See `corpus-retrieval.md`. |
| `member` | A person on the team. | `team_pulse_resources(type="member")`, `team_pulse_get(id="members/<handle>")` |
| `question` | Admin-authored reflection prompts the team is currently being asked. | `team_pulse_resources(type="question")`, `team_pulse_get(id="questions/<slug>")` |

`team_pulse_info().resource_types` is the list of valid `type=` values right now
(e.g. `["member", "question"]`). A `type=` outside that list returns **400
`unsupported_type`** — that's by design, not an error to route around: if you
find yourself wanting a type that isn't listed, the answer lives in the corpus,
not a structured type. `team_pulse_info().collections` lists the content
collections; pass those names as `collection=`.

### The list / single-resource envelopes

Single resource:

```json
{
  "id":       "members/alice",
  "title":    "Alice",
  "type":     "member",
  "data":     { /* the canonical resource body */ },
  "metadata": { /* last_modified, etc. */ }
}
```

List (cheap — ID/title/type only; get the full body with `team_pulse_get`):

```json
{
  "resources": [
    {"id": "members/alice", "title": "Alice", "type": "member"},
    /* ... */
  ],
  "count": 18
}
```

**Content-collection pages** (corpus pages) come back with the markdown body in
a top-level **`content`** field instead of a structured `data` dict — switch on
the top-level `type`/shape:

* structured entity (`member`/`question`) → read `data`
* content page (`corpus/...`) → read `content` (raw markdown string)

### The error envelope

```json
{"error": {"code": "not_found", "message": "...", "status": 404}}
```

Every error path uses this shape. The tool layer surfaces it verbatim in
`ToolResult.error` — you can quote `error.message` back to the user.

## Endpoint reference (mapped to tools)

| Tool | Wraps | When to use |
|---|---|---|
| `team_pulse_info()` | `GET /api/lens/info` | **First call to orient.** Returns the live catalog of resource types + content collections. Answer "what can Team Pulse tell me?" by CALLING this, not from memory. |
| `team_pulse_search(q=…, collection=…)` | `GET /api/lens/resources/search` | Find the specific corpus page (or member/question) matching a term. A bare query searches the corpus; pass `collection` to scope deterministically. |
| `team_pulse_prefix(prefix)` | `GET /api/lens/resources/prefix/{p}` | Hierarchical listing — e.g. `prefix("members")`, or drill a corpus sub-corpus `prefix("corpus/<sub>/")`. |
| `team_pulse_resources(type=… \| collection=…)` | `GET /api/lens/resources` | List members/questions (`type=`) or a corpus collection (`collection=`). Read `count`/`total`; page with `limit`/`offset`. |
| `team_pulse_get(id=…)` | `GET /api/lens/resources/{id}` | Fetch one resource/page by full ID. Do NOT `get` a giant index/overview/log page in full — locate the specific page first (see `corpus-retrieval.md` §2). |
| `team_pulse_graph()` | `GET /api/lens/graph` | Raw structural entity graph + reverse edges. **May include frozen/aging data — not a current-state source.** Large payload; use sparingly for structural relationships, and prefer the corpus for what's actually happening. |
| `team_pulse_ask(prompt=…)` | `POST /api/lens/ask` | **Online generation** — only when the user names Team Pulse as the answerer. Returns a corpus-grounded synthesized answer that cites `tp://doc/…` sources. |
| `team_pulse_download_corpus(dest_dir=…)` | `GET /api/lens/corpus/download` | Offline/bulk: extract the corpus `.md` tree to disk for your own grep/embeddings. Not for answering a single question. See `corpus-retrieval.md` §8. |

## Common query patterns

The corpus is the answer surface for almost every "about the team's work"
question. Discover the collection names from `/info`, then scope to them.

### "What's the team doing / what shipped in area X?"

```python
team_pulse_info()                                   # collection names + sub_corpora
team_pulse_search(q="<area/topic>", collection="corpus")
team_pulse_get(id="corpus/<sub>/<specific-page>.md")  # the ONE matching page
```

Cite the page and its sub-corpus `last_updated` ("as of …"). See
`corpus-retrieval.md` §1–§4.

### "Who owns / who's working on X?" and "what did we decide about X?"

These are corpus questions, not structured-type questions. Search the corpus
(conversation/decision sub-corpus for the decision; code/repo sub-corpus for the
implementation) and JOIN the two sides with provenance — `corpus-retrieval.md`
§6 is the playbook. Do **not** answer from pretraining; **retrieve, don't
recall.**

### "Who is on the team?" / member lookup

```python
team_pulse_resources(type="member")          # roster; read result.count
team_pulse_get(id="members/<handle>")        # one member's record
team_pulse_prefix("members")                 # browse the namespace
```

`member` is a real structured type — this is the one "roster" question that is
NOT a corpus lookup.

### Fuzzy lookup

```python
team_pulse_search(q="<term>", collection="corpus", limit=20)
```

Returns a list envelope. Use the IDs to follow up with `team_pulse_get` for the
specific page's full body. (For sub-corpus scoping, pagination, and the
big-file crash-guard, see `corpus-retrieval.md`.)

### Working with questions

Reflection questions are the admin's "what should the team be thinking
about right now" surface. They use the standard entity envelope (body in
`data`, not `content`), so all the generic tools work without special
casing:

```python
# List every active question — read result.count for the total
# Returned in (created_at, id) order so display order follows authoring order.
team_pulse_resources(type="question")

# Fetch one question by its full hierarchical ID
team_pulse_get(id="questions/hard-questions")
# result.data is the question dict: {id, text, created_at, created_by}
# result.title is the question text (questions have no separate title field)

# Browse the whole namespace
team_pulse_prefix("questions")
```

Question schema (v0):

| Field | Notes |
|---|---|
| `id` | Admin-authored kebab-case slug (e.g. `hard-questions`, `effective-practices`). Stable opaque identifier — survives text edits because text edits aren't allowed (see immutability note). NOT a content hash. |
| `text` | The prompt itself. **Immutable** in v0 — typo fixes require a new slug. |
| `created_at` | ISO-8601 UTC timestamp the admin first added the question. Also serves as the sort key for display order. |
| `created_by` | The admin's short handle. |

The v0 surface is intentionally minimal: there is no `state` field,
no explicit `display_order` field, no `schema_version` yet. All three
are pure-additive and will arrive when needed without breaking this
contract. Ordering today is `(created_at, id)` from the loader; when
a UI exists that needs to support reorder, `display_order: int | null`
can be added without disturbing existing consumers.

Forward-compat: an answer references a question by its bare slug
(`question_id: "hard-questions"`, not `"questions/hard-questions"`) —
matching the FK convention used throughout the surface (references use bare
handles/slugs, not hierarchical IDs). The immutability rule means old answers
stay valid; if the admin wants to reword a question, they create a new slug and
archive the old one — answers to the old slug remain meaningful.

### Working with answers

Answers are the responses to reflection questions. The bundle exposes one
write tool for submitting session-mined answers. There is no read tool for
answers in v0 — answer read access is handled by the team-pulse app UI.

#### Submitting an answer (`team_pulse_submit_answer`)

Use this tool to record an AI-generated answer attributed to a specific team
member, synthesized from their Context Intelligence sessions.

**Parameters:**

| Parameter | Required | Notes |
|---|---|---|
| `question_id` | yes | **Bare slug** — e.g. `higher-level-work`, NOT `questions/higher-level-work`. Strip the `questions/` prefix if you have it from a resource lookup. |
| `user_id` | yes | GitHub username of the person the answer is about (e.g. `jdoe`). The bundle records it as a github-namespaced identity (the API stores it verbatim and resolves to a team member at read time). |
| `answer` | yes | The answer body. Min length 1. |
| `generated_at` | yes | ISO-8601 timestamp when the answer was generated (e.g. `2026-05-31T02:15:30.000+00:00`). |
| `metadata` | no | Opaque bag stored **verbatim** by the server. **Session provenance lives here**: pass `source_session_ids` (array of Context Intelligence session IDs) inside `metadata`. May also carry timing, model, confidence, etc. Omit for a bare submit. |

**`question_id` must be a bare slug.** The pattern `^[a-z0-9][a-z0-9-]*$` is
enforced at the schema level. If you have a hierarchical ID from a resource
lookup (`questions/higher-level-work`), strip the `questions/` prefix before
passing it here. This matches the FK convention used throughout the surface
(references use bare handles/slugs, not hierarchical IDs).

**Error codes** you may see from the server:

| Code | When |
|---|---|
| `unknown_question` | `question_id` doesn't match a known question |
| `unknown_respondent` | `user_id` resolves to no member of the team |
| `invalid_argument` | missing/empty required field, unparseable `generated_at` |

#### Worked example: discover question → submit answer

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

The server returns the persisted record on `201`; metadata is echoed back verbatim with session provenance inside it.

### team_pulse_ask — online-generation doorway

`team_pulse_ask` is the **online-generation** tool. Unlike the read-only
`team_pulse_*` data tools (which return raw pages/facts), `team_pulse_ask`
composes a synthesized answer **grounded in the corpus** by calling
`POST /api/lens/ask`; its answer cites `tp://doc/…` sources.

Use it only when the user names Team Pulse as the answerer (see "Tool selection"
above) — not on your own initiative.

**Parameters:**

| Parameter | Required | Notes |
|---|---|---|
| `prompt` | yes | The question to ask. Min length 1. |
| `focus` | no | Optional lens resource id (e.g. `members/alice`). Used as an **orientation hint** — the server prepends one line `## Currently viewing\n{focus}` to the user message. Not a filter; does not isolate the answer to that resource. |

**`viewer` is never a caller parameter.** The server derives the viewer
identity from the api-key/bearer principal. You never pass `viewer`.

**Response shape (`AskResponse`):**

```json
{
  "content":     "## Team\n\n- **alice** is on the migration…",
  "prompt_used": "the prompt sent to the generator",
  "provenance":  {
    "sources":      [{"type": "sessions", "count": 4, "date_range": "retrieved"}],
    "generated_at": "2026-06-15T10:00:00"
  }
}
```

The `content` field is **markdown text** the agent can read and reason over
directly. There is no `html`, no `pills`, and no `fallback` field. `provenance.sources`
reflects the corpus documents the answer drew on.

**Fail-loud behavior.** There is no silent fallback. If the LLM generation
engine is unavailable, the API returns **HTTP 500** — surfaced to the tool
caller as a `TeamPulseAPIError` with `status: 500`. Do not retry
automatically; surface the error to the user.

**Worked example:**

```python
# Ask a general question (only when the user names Team Pulse as the answerer)
result = team_pulse_ask(prompt="How is the team tracking on the migration?")
# result.output["content"] contains the markdown answer

# Ask with focus orientation
result = team_pulse_ask(
    prompt="What's the status?",
    focus="members/alice",
)
# The server prepends "## Currently viewing\nmembers/alice" to the prompt
# before generation — an orientation hint, not a filter.
```

## Content collections (the corpus)

The corpus is exposed as one or more named content collections of `.md` pages.
This section is the quick mechanic; the full skill is in `corpus-retrieval.md`.

1. **Discover** — `team_pulse_info()` returns a `collections` array and, per
   collection, a `sub_corpora[]` map with `{name, summary, last_updated,
   entry_points}`. Read names/freshness from here; never assume them.

2. **Scope** — pass `collection=<name>` to `team_pulse_search` / `team_pulse_resources`:

   ```python
   team_pulse_search(q="<topic>", collection="corpus")
   team_pulse_resources(collection="corpus", limit=50)   # paginate; read total
   ```

3. **Read one page** — `team_pulse_get` with the full ID from the list
   (`<collection>/<sub>/<path>.md`). Locate the specific page first; do not
   full-read a big index/overview/log page (`corpus-retrieval.md` §2).

## Error handling guidance

* **404** → the resource ID is wrong or doesn't exist. Try
  `team_pulse_prefix(...)` to discover valid IDs in that namespace, or
  `team_pulse_search(q=…, collection="corpus")` for fuzzy lookup.
* **400 `unsupported_type`** → you passed a `type=` that isn't currently served
  (the structured surface is `member`/`question`). The answer is in the corpus —
  re-scope to `collection="corpus"`. Re-check `team_pulse_info()` for the live types.
* **401 / missing_or_malformed_key** → the bundle's `key` config is
  unset, mistyped, or revoked. Surface the error code to the user; do
  NOT retry blindly.
* **transport_error** → network / DNS / timeout. Show the message; the
  caller decides whether to retry.

## Scope reminder (v1)

These tools answer **factual** questions grounded in the corpus and the member /
question surface. They do NOT theorize about whether work is at risk, or what
someone *should* be doing. That's a "thinking partner" role deferred to a future
agent. If the user asks for analysis, surface the retrieved facts (with
citations and freshness) and let the parent session reason about them. And when
you don't have a retrieved source: say so — **retrieve, don't recall**; never
fabricate a fact, a PR number, or a source.
