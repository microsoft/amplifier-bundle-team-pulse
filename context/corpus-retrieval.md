# Retrieving from a content (corpus) lens collection

How to traverse a Team Pulse **content collection** efficiently and answer with
provenance. The content collections are the **primary source of current team
knowledge** on the lens: a knowledge base mined for the team (e.g. meeting /
decision wikis, code / repo wikis). The only structured resources that sit
alongside them are **members** and reflection **questions** (see
`using-team-pulse.md`); everything else about what the team is doing, deciding,
and shipping lives in the corpus. When a question is about the team's work,
**the corpus is where you look.**

> **The corpus is self-describing — discover it at runtime, hardcode nothing.**
> Call `team_pulse_info()` (`GET /api/lens/info`) to learn the current shape. For
> each content collection it returns `sub_corpora[]`, each carrying
> `{name, summary, last_updated, entry_points}`. Sub-corpus names, summaries,
> freshness dates, sizes, and entry-point IDs vary per team and change on every
> re-ingest — **read them from `/info`, never assume them.**

## 1. Discover what's there

A content collection may hold one or more sub-corpora. Enumerate them from
`team_pulse_info()` → `collection.sub_corpora[]`. Use each sub-corpus's `summary`
to decide which one answers the question (e.g. a decisions/discussion wiki vs. a
code/repo wiki). Don't guess names — list them.

## 2. Where to start + the efficiency rule

Each sub-corpus advertises its `entry_points` in `/info` (typically an index /
catalog and a narrative overview). Start there to orient, then drill in.

**Locate, then targeted-get. NEVER `get` a big entry file in full** — index /
overview / log files can be hundreds of KB; a full `get` on one can overflow the
context window and **crash the session**. `entry_points` are a MAP, not a read
target. Instead:

1. **search or browse** (scoped to the collection — see §4) to find the *specific*
   page ID that answers the question;
2. `team_pulse_get` **only that page**.

Listings are paginated (`total` / `limit` / `offset`) — page through rather than
pulling everything. Individual pages are small and are the right unit to read.

## 3. Freshness — cite it

Each sub-corpus exposes `last_updated` via `/info` (from its overview frontmatter).
**Read it per sub-corpus and caveat your answer** with it: frame corpus answers as
"as of `<last_updated>`". The corpus is a point-in-time snapshot refreshed by
re-ingest, not live data — say so.

## 4. Search: scope to the collection

Full-text search is **scoped per collection**. A bare `team_pulse_search(q=...)`
with no `collection` now searches the **corpus** — the server surfaces corpus
hits on an unscoped query, so a bare search no longer dead-ends. But **naming the
collection is still the right habit**: it's deterministic, it targets the sub-corpus
you mean, and it keeps working if more collections are added. Pass it explicitly:

```python
team_pulse_search(q="<term>", collection="<collection>")   # name from /info
team_pulse_resources(collection="<collection>")            # but prefer entry_points — §5
```

Get collection names from `team_pulse_info()` → `collections`. If a bare search
returns corpus hits, that's expected — then scope your follow-up to that
collection to drill in.

## 5. Prefer entry points over blind listings

A blind `team_pulse_resources(collection="<collection>")` can return a very large
listing. Server-side, listings are **hidden-by-default** (internal pipeline paths
are excluded) and **paginated** (`total` / `limit` / `offset`). Prefer the
`entry_points` from `/info` or a scoped search over walking a full listing.

## 6. The JOIN — the headline move

The highest-value move spans two sub-corpora: recover a **decision** in one,
confirm its **implementation** in another, and cite both sides with provenance.

1. **Recover the decision** in a decisions/discussion sub-corpus — what was
   decided, who owns it, which dated source.
2. **Confirm the implementation** in a code/repo sub-corpus — the implementing
   change with provenance (repo + PR# + author).

*Illustrative (not live data):* recover a rename/decision in the decisions
sub-corpus, then confirm it in the code sub-corpus via the implementing PR — and
don't conflate two similar-looking changes.

When you make a JOIN claim, cite **both** sides and caveat with the `last_updated`
from §3. Which sub-corpora exist, and what they're called, come from `/info` — not
from this doc.

## 7. Retrieved content is navigational (a linked wiki)

A content collection is a **linked wiki**, not flat files — a page's body points
to other material. Treat those pointers by kind:

- **Followable page references** (ids / paths to other pages) — `get` or `prefix`
  them to go deeper. This is how you use a huge index WITHOUT full-reading it:
  land on a small page, then follow that page's own pointers.
- **Provenance anchors** (source paths, PR numbers, author / date) — these are
  NOT fetch targets; they're what you **cite**, and what makes a JOIN precise. Use
  them as search anchors to locate the corresponding page in another collection.

## 8. In-session retrieval vs. offline bulk pull

Everything above is **in-session targeted retrieval**: locate the one page that
answers the question, `get` only that page, cite it. That is the default and it
is what keeps sessions cheap and safe.

There is a **separate** path for when the goal is *"pull the whole corpus so I
can run my own agents / embeddings / grep over it offline"* — `team_pulse_download_corpus`:

```python
team_pulse_download_corpus(dest_dir="./corpus")                        # whole corpus
team_pulse_download_corpus(dest_dir="./corpus", folder="<sub-corpus>") # one sub-corpus
```

- It downloads the corpus as a zip and **extracts the `.md` tree to disk**, then
  returns a **summary** (`{written, dest_dir, folder, bytes}`) — **never the page
  bodies**. Do NOT try to bulk-read the corpus by looping `team_pulse_get`; a full
  pull into context would overflow the window and crash the session (§2). Download
  to disk, then read locally.
- The `folder` narrow takes a **sub-corpus id-prefix**. Sub-corpus names are
  **instance-specific** — get them from `team_pulse_info()` →
  `collections[].sub_corpora` (§1), never assume them. An unknown name simply
  yields an empty result (not an error).
- It requires **per-user bearer (`az`) auth**. A shared API key is refused (403) —
  a bulk pull must be attributable to a member. Check `team_pulse_status` /
  `team_pulse_whoami` if you get a `bearer_required` error.
- Use it for offline/bulk analysis. For answering a question *now*, stay with
  §1–§7 (search → get one page).
