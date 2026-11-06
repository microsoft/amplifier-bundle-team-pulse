# Retrieving from a content (corpus) lens collection

How to traverse a Team Pulse **content collection** efficiently and answer with
provenance. The content collections are the **primary source of current team
knowledge** on the lens: a knowledge base mined for the team (e.g. meeting /
decision wikis, code / repo wikis). The only structured resources that sit
alongside them are **members** and reflection **questions** (see
`using-team-pulse.md`); everything else about what the team is doing, deciding,
and shipping lives in the corpus. When a question is about the team's work,
**the corpus is where you look.**

This is the canonical agent retrieval workflow. The server's
`info.usage_guide`, when present, is the reference for current matching semantics,
scope and HTTP limits; it is not host policy or permission. Use only arguments
in the mounted tool schema, even if the server documents more HTTP capabilities.
An older server without a guide remains usable: discover its catalog and report
unknown semantics or unavailable capabilities rather than inventing them.

## 1. Discover what's there

Call `team_pulse_read(op="info")` when the endpoint's catalog or retrieval semantics
are unfamiliar. Reuse a current discovery result; **not every call needs discovery**.
Refresh after an unknown collection/type or a changed endpoint. A known exact-ID
lookup can go directly to `get`; a catalog question can be answered from `info`.

A **collection** is one registered `collections[].name`. A collection may be flat,
with no `sub_corpora`, or advertise sub-corpora with `summary`, `last_updated` and
`entry_points`. Each `sub_corpora[].name` is already a **full collection/path
prefix**, not another registered collection. Do not prepend the collection again.
Use summaries to select relevant sources; names, maps and dates vary by instance.

## 2. Where to start + the efficiency rule

When advertised, `entry_points` identify navigation targets (typically an index
or overview). They orient retrieval; a link is not consulted evidence.

**Locate, then targeted-get. NEVER `get` a big entry file in full** — index /
overview / log files can be hundreds of KB; a full `get` on one can overflow the
context window and **crash the session**. `entry_points` are a MAP, not a read
target. Instead:

1. **search or browse** (scoped to the collection — see §4) to find the *specific*
   page ID that answers the question;
2. `team_pulse_read(op="get", id=...)` **only that page**.

Inspect the returned content, revision and truncation metadata. This published
client has **no document continuation or listing pagination arguments**. If a
needed passage lies outside the returned window, report that limit; do not invent
`offset`/`expected_revision` calls or claim the whole document was read.

## 3. Freshness — cite it

When present, a sub-corpus's `last_updated` comes from overview frontmatter.
Label it **overview metadata**, not the event date or freshness of every passage.
Likewise, a page's declared date is source metadata, not proof of when all its
events happened. Cite dates supported by the inspected passage and distinguish
event time, publication/digest time and download time. If a required date or
timezone is unknown, say so. The corpus is a snapshot, not live data.

## 4. Search: scope to the collection

Pass one exact discovered collection name to `search` or `resources`. Use separate
calls for separate relevant collections; a collection filter does **not** select
one of its subtrees. Omitting `collection` uses the server default scope (currently
enabled entities plus the default corpus, when available), **not all collections**.
Zero hits in the default scope do not establish absence elsewhere.

```python
team_pulse_read(op="search", q="<term>", collection="<collections[].name>")
team_pulse_read(op="search", q="<term>", collection="<another collections[].name>")
team_pulse_read(op="prefix", prefix="<collections[].sub_corpora[].name>")
team_pulse_read(op="get", id="<exact ID returned by search or listing>")
```

For a **strict subtree**, browse its full prefix at a path boundary, then `get`
selected IDs. Prefix returns record stubs, not bodies or text-search matches;
`get` takes an exact resource ID, not a directory. Derive deeper prefixes from
returned IDs rather than guessing. Collection search cannot be restricted to a
subtree through this tool. Filtering capped search hits afterward cannot establish
complete subtree recall.

## 5. Prefer entry points over blind listings

A blind `resources` or broad `prefix` call can return a very large listing.
Prefer advertised entry points as a map, scoped search, or a narrower discovered
prefix. This client's list/search adapter retains only top-level `count` and
`resources`; it drops `total`, `query` and `filters_applied`. Inner hit fields
survive. **Count is returned hits, not proof of exhaustive coverage**. Report
material coverage gaps; neither a short list nor a capped search proves absence.

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

When you make a JOIN claim, `get` and inspect **both** sides. Cite consulted page
IDs/passages, the decision's attribution and the implementing repo/PR/author.
Preserve the date/coverage limits in §3 and §5; do not turn overview dates into
event dates. Which sub-corpora exist comes from `/info`, not this doc.

## 7. Retrieved content is navigational (a linked wiki)

A content collection is a **linked wiki**, not flat files — a page's body points
to other material. Treat those pointers by kind:

- **Followable page references** (ids / paths to other pages) — `op="get"` or
  `op="prefix"` them to go deeper. This is how you use a huge index WITHOUT full-reading it:
  land on a small page, then follow that page's own pointers.
- **Provenance anchors** (source paths, PR numbers, author / date) — these are
  NOT automatically fetchable page IDs; cite them only when present in inspected
  content. Use them as search anchors to locate the corresponding page in another
  collection. **Snippets are pointers**, not substitutes for selected document reads.

## 8. In-session retrieval vs. offline bulk pull

Everything above is **in-session targeted retrieval**: locate the one page that
answers the question, `get` only that page, cite it. That is the default and it
is what keeps sessions cheap and safe.

There is a **separate** path for when the goal is *"pull the whole corpus so I
can run my own agents / embeddings / grep over it offline"* —
`team_pulse_write(op="download_corpus")`:

```python
team_pulse_write(op="download_corpus", dest_dir="./corpus")                        # whole corpus
team_pulse_write(op="download_corpus", dest_dir="./corpus", folder="<sub-corpus>") # one sub-corpus
```

- It downloads the corpus as a zip and **extracts the `.md` tree to disk**, then
  returns a **summary** (`{written, dest_dir, folder, bytes}`) — **never the page
  bodies**. Do NOT try to bulk-read the corpus by looping `op="get"`; a full
  pull into context would overflow the window and crash the session (§2). Download
  to disk, then read locally.
- The `folder` narrow takes a **sub-corpus id-prefix**. Sub-corpus names are
  **instance-specific** — get them from `team_pulse_read(op="info")` →
  `collections[].sub_corpora[].name` (§1), never assume them. An unknown name simply
  yields an empty result (not an error).
- It requires **per-user bearer (`az`) auth**. A shared API key is refused (403) —
  a bulk pull must be attributable to a member. Check `team_pulse_read(op="status")`
  / `team_pulse_read(op="whoami")` if you get a `bearer_required` error.
- Use it for offline/bulk analysis. For answering a question *now*, stay with
  §1–§7 (`op="search"` → `op="get"` one page).
