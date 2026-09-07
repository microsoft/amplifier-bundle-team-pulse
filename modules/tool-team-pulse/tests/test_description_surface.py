# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Head-surface guard for the 12 ``team_pulse_*`` tool descriptions.

Tool descriptions are always-on context: every one of them is rendered into the
system prompt of every session that loads this bundle, whether or not team-pulse
is ever called.  That makes them expensive, and it makes silent drift in them
expensive too.

Three things are pinned here:

1. **Byte pins.**  Every description's exact SHA-256.  A description cannot
   change -- in either direction -- without this test failing and the author
   consciously re-pinning it.  Three descriptions were already trigger-first and
   tight when the surface was leaned; their pins are the ORIGINAL bytes, so
   "preserved byte-for-byte" is a machine-checked claim, not a promise.

2. **Semantic fidelity.**  Every behaviour, constraint, parameter semantic and
   failure mode carried by the pre-lean descriptions, enumerated one row at a
   time with a probe that must still match the current text.  Leaning the
   surface must never drop a semantic; ``test_no_semantic_is_absent`` is the
   thing that makes that checkable rather than asserted.

3. **Shape rules.**  Length cap, and no ``<example>``/``<commentary>`` blocks --
   those belong in agent definitions, never in an always-on tool description.

Run: ``pytest modules/tool-team-pulse/tests/test_description_surface.py``
"""

from __future__ import annotations

import hashlib
import re

import pytest

from amplifier_module_tool_team_pulse.tool import _DATA_TOOL_CLASSES, TeamPulseConfigureTool

# --- the surface under test ------------------------------------------------

#: name -> description for all 12 always-on team-pulse tools.
DESCRIPTIONS: dict[str, str] = {c.name: c.description for c in _DATA_TOOL_CLASSES}
DESCRIPTIONS[TeamPulseConfigureTool.name] = TeamPulseConfigureTool.description

EXPECTED_TOOL_COUNT = 12

# --- 1. byte pins -----------------------------------------------------------

#: SHA-256 of each description as it stands.  Changing a description is fine --
#: changing it *without noticing* is not.  Re-pin deliberately.
DESCRIPTION_SHA256: dict[str, str] = {
    "team_pulse_ask": "959c872a0da498b5a2665a7a524204531ddc04c10f0adb60e6116ba0efbfa414",
    "team_pulse_configure": "3d5cd169b14c54c7745f645308967fbb6d778eecc92262fefd723776070850f9",
    "team_pulse_download_corpus": "6acd1fb7fab1c059ed9a3c84364e08f532d1f9a5a042ec3638028a0edb5e0825",
    "team_pulse_get": "6485b0b659e6841364f46f69f860e2d77d69151353c131670e72a57a13051301",
    "team_pulse_graph": "50b51b71daa8117c83a03823d57e13b7725ab7817d0cf8b5d0aa60f0c56a2ad6",
    "team_pulse_info": "9063be5e7f1ee945b6ee9e989f1c2754b40170e72543fe94e4645bc5440a0602",
    "team_pulse_prefix": "383bd9e07f6e5872a0d766b28123efdff6e91a70520a2007bc70253ab9ef29ae",
    "team_pulse_resources": "2fe601fb83d5231d1d82d46dc5f47f3f990d8a32a1d08de784b68b32b09c3cb8",
    "team_pulse_search": "0b984e7cec4ef346934c9b0e1fdfa7e71653b9c1e6d5cfaa756e259e5b841678",
    "team_pulse_status": "c6f24275dafbf07bf91973c74b3e8c378bb87e9251e289a7232a011ee779f4f4",
    "team_pulse_submit_answer": "9b9cb4b3fe68c371e33e16190bebd51a9a5a22da789e125183b523a438e37412",
    "team_pulse_whoami": "e89e3bab20adfa8caf6701dc141a3bd87dd4ef788b6b1c71d9cd286bef0d9c85",
}

#: Descriptions that were ALREADY trigger-first and tight, and so were left
#: untouched by the leaning pass.  These pins are the pre-lean bytes: if one of
#: these ever changes, the "preserved byte-for-byte" claim is false and this
#: test says so.  (Same hashes as DESCRIPTION_SHA256 above -- restated here so
#: the intent, not just the value, is recorded.)
PRESERVED_BYTE_FOR_BYTE: dict[str, str] = {
    "team_pulse_get": "6485b0b659e6841364f46f69f860e2d77d69151353c131670e72a57a13051301",
    "team_pulse_prefix": "383bd9e07f6e5872a0d766b28123efdff6e91a70520a2007bc70253ab9ef29ae",
    "team_pulse_search": "0b984e7cec4ef346934c9b0e1fdfa7e71653b9c1e6d5cfaa756e259e5b841678",
}

# --- 3. shape rules ---------------------------------------------------------

#: Soft cap on an always-on description.
LENGTH_CAP = 600

#: Descriptions permitted past the cap, each because it carries a *named*
#: parameter (or named response-field) contract that the JSON schema alone does
#: not express -- the one exemption the head-surface rule allows.  The value is
#: the contract that earns the exemption.
CAP_EXEMPT: dict[str, str] = {
    "team_pulse_submit_answer": "question_id / user_id / generated_at / metadata contracts",
    "team_pulse_download_corpus": "dest_dir / folder contracts + bearer-only auth rule",
    "team_pulse_status": "the exact response field list it promises",
    "team_pulse_configure": "client_id + AMPLIFIER_TEAM_PULSE_KEY precedence contract",
}

# --- 2. semantic fidelity ---------------------------------------------------
#
# Every row is one semantic carried by the PRE-LEAN description.  `probe` is a
# case-insensitive regex that must still match the CURRENT description.
# Expected absent count: 0.

Semantic = tuple[str, str, str]  # (id, what it asserts, probe regex)

SEMANTICS: dict[str, list[Semantic]] = {
    "team_pulse_info": [
        ("INFO-1", "describes the SERVER, not the client", r"SERVER"),
        ("INFO-2", "remote: needs network and working auth", r"[Rr]emote.*network.*auth"),
        ("INFO-3", "returns API name/version", r"name/version"),
        ("INFO-4", "returns the auth scheme the server documents", r"auth scheme it documents"),
        ("INFO-5", "returns capabilities", r"capabilities"),
        ("INFO-6", "returns the endpoint catalog", r"endpoint catalog"),
        ("INFO-7", "returns content collections", r"content collections"),
        ("INFO-8", "use it to discover what the API exposes", r"[Dd]iscover what the API exposes"),
        ("INFO-9", "does NOT report your URL or how you authenticated", r"NOT which URL.*how you\s+authenticated"),
        ("INFO-10", "client's resolved config is team_pulse_status", r"team_pulse_status"),
    ],
    "team_pulse_resources": [
        ("RES-1", "lists team-pulse resources", r"List team-pulse resources"),
        ("RES-2", "returns the list envelope shape", r"\{resources: \[\{id, title, type\}\], count\}"),
        ("RES-3", "type narrows to one resource class", r"`type` narrows to one resource\s+class"),
        ("RES-4", "valid types are server-defined and vary by deployment", r"server-defined and vary by deployment"),
        ("RES-5", "check team_pulse_info()'s resource_types first", r"team_pulse_info\(\)'s resource_types"),
        ("RES-6", "unsupported type returns HTTP 400", r"unsupported type -> HTTP 400"),
        ("RES-7", "status selects lifecycle state for type=question", r"active \| archived \| all.*type=question"),
        ("RES-8", "default active hides archived", r"default active hides archived"),
        ("RES-9", "collection lists a content collection folder", r"`collection` lists a content-collection folder"),
    ],
    "team_pulse_search": [
        ("SRCH-1", "naive text search across all resources", r"[Nn]aive text search across all team-pulse resources"),
        ("SRCH-2", "same list envelope as team_pulse_resources", r"same list envelope as team_pulse_resources"),
        ("SRCH-3", "default limit 50, max 200", r"[Dd]efault limit 50, max 200"),
        ("SRCH-4", "search is substring-matchy", r"substring-matchy"),
        ("SRCH-5", "prefer get/prefix for precise ID lookups", r"team_pulse_get or team_pulse_prefix"),
    ],
    "team_pulse_prefix": [
        ("PFX-1", "lists resources whose ID starts with a prefix", r"ID starts with the given path prefix"),
        ("PFX-2", "worked example", r"prefix='projects'"),
        (
            "PFX-3",
            "cheaper/more precise than search for hierarchy",
            r"[Cc]heaper and more precise than team_pulse_search",
        ),
    ],
    "team_pulse_get": [
        ("GET-1", "fetch a single resource by full ID", r"single resource by full ID"),
        ("GET-2", "returns the resource envelope shape", r"\{id, title, type, data, metadata\}"),
        ("GET-3", "ID shape is <type>/<slug> with examples", r"'<type>/<slug>'.*members/jdoe"),
        ("GET-4", "types are server-defined; see info's resource_types", r"team_pulse_info\(\)'s resource_types"),
        ("GET-5", "404 envelope if unknown", r"404 envelope if unknown"),
    ],
    "team_pulse_graph": [
        ("GRPH-1", "full composed entity graph", r"full composed entity graph"),
        ("GRPH-2", "every resource of every type", r"every resource of every type"),
        ("GRPH-3", "plus computed reverse edges", r"computed reverse edges"),
        ("GRPH-4", "in one response", r"in one response"),
        ("GRPH-5", "large payload", r"[Ll]arge payload"),
        (
            "GRPH-6",
            "prefer resources/get for targeted lookups",
            r"team_pulse_resources / team_pulse_get for targeted lookups",
        ),
        ("GRPH-7", "use for cross-resource relationships", r"cross-resource relationships"),
        ("GRPH-8", "worked examples of those relationships", r"who's on what.*roll up to which initiative"),
    ],
    "team_pulse_whoami": [
        ("WHO-1", "resolves the current caller's identity", r"[Rr]esolve the caller's identity"),
        ("WHO-2", "for me/my/mine phrasing", r"'me' / 'my' / 'mine'"),
        ("WHO-3", "worked examples of that phrasing", r"my projects.*my record.*what am I assigned"),
        ("WHO-4", "takes no input", r"[Tt]akes no input"),
        ("WHO-5", "returns how the caller authenticated", r"how the caller authenticated"),
        ("WHO-6", "returns whether a per-user identity is available", r"per-user identity is available"),
        (
            "WHO-7",
            "SERVER-verified identity (handle/member_id)",
            r"SERVER-verified team-pulse identity\s+\(handle/member_id\)",
        ),
        ("WHO-8", "distinct from status's az_identity_hint", r"team_pulse_status\(\)'s az_identity_hint"),
        ("WHO-9", "that hint is a raw, unverified Azure token claim", r"raw, unverified Azure token\s+claim"),
        ("WHO-10", "and may not match", r"may not match"),
    ],
    "team_pulse_ask": [
        ("ASK-1", "ask is server-side ONLINE GENERATION", r"server-side ONLINE GENERATION"),
        (
            "ASK-2",
            "a Team Pulse LLM composes a bounded answer over current team data",
            r"Team Pulse LLM composes a bounded answer\s+over current team data",
        ),
        ("ASK-3", "prefer the read tools by default", r"BY DEFAULT PREFER THE READ TOOLS"),
        (
            "ASK-4",
            "names the four read tools",
            r"team_pulse_info / team_pulse_search / team_pulse_get / team_pulse_resources",
        ),
        (
            "ASK-5",
            "read the corpus and compose the answer yourself",
            r"read the corpus and compose the answer yourself",
        ),
        ("ASK-6", "the read tools are cheaper", r"cheaper"),
        ("ASK-7", "the read tools return full-fidelity data", r"full-fidelity\s+data"),
        (
            "ASK-8",
            "you are already an LLM that can synthesize from raw reads",
            r"already an LLM that can synthesize from raw reads",
        ),
        (
            "ASK-9",
            "call ONLY on explicit user direction",
            r"ONLY when the user explicitly directs Team Pulse to answer",
        ),
    ],
    "team_pulse_download_corpus": [
        ("DL-1", "bulk-download the whole mined corpus", r"Bulk-download the whole mined corpus"),
        ("DL-2", "every sub-corpus the server exposes", r"every sub-corpus the server exposes"),
        ("DL-3", "to a LOCAL DIRECTORY", r"LOCAL DIRECTORY"),
        (
            "DL-4",
            "for your own agents / embeddings / grep, offline",
            r"own agents / embeddings / grep over it\s+offline",
        ),
        ("DL-5", "one zip fetch", r"[Oo]ne zip fetch"),
        ("DL-6", "extracts the .md tree under dest_dir", r"\.md tree under dest_dir"),
        ("DL-7", "returns the SUMMARY shape", r"SUMMARY \{written, dest_dir, folder, bytes\}"),
        ("DL-8", "NOT the page bodies", r"NOT the page bodies"),
        (
            "DL-9",
            "because hundreds of docs would crash the session",
            r"hundreds of docs into context would crash the session",
        ),
        ("DL-10", "this is the offline BULK path", r"[Oo]ffline BULK path"),
        ("DL-11", "in-session Q&A goes to search/get", r"in-session Q&A goes to team_pulse_search / team_pulse_get"),
        ("DL-12", "requires per-user BEARER (az) auth", r"per-user BEARER \(az\) auth"),
        ("DL-13", "a shared API key is refused with 403", r"shared API key is refused \(403\)"),
        ("DL-14", "because a bulk pull must be attributable to a member", r"attributable to a member"),
        ("DL-15", "optional folder narrows to ONE sub-corpus", r"[Oo]ptional folder narrows to ONE\s+sub-corpus"),
        ("DL-16", "sub-corpus names are instance-specific", r"names are instance-specific"),
        (
            "DL-17",
            "discover them from info(); never assume",
            r"team_pulse_info\(\) \(collections\[\]\.sub_corpora\), never assume them",
        ),
    ],
    "team_pulse_submit_answer": [
        (
            "SUB-1",
            "submit a session-mined answer to a reflection question",
            r"session-mined answer to a team-pulse reflection question",
        ),
        (
            "SUB-2",
            "records an AI-generated answer attributed to a specific user",
            r"AI-generated answer attributed to a specific user",
        ),
        (
            "SUB-3",
            "synthesized from their Context Intelligence sessions",
            r"synthesized from their\s+Context Intelligence sessions",
        ),
        (
            "SUB-4",
            "question_id is the BARE SLUG, with an example",
            r"question_id: the BARE SLUG \(e\.g\. 'higher-level-work'\)",
        ),
        ("SUB-5", "NOT the hierarchical questions/<slug> form", r"NOT hierarchical\s+'questions/<slug>'"),
        ("SUB-6", "strip the prefix if you have it", r"strip that prefix"),
        ("SUB-7", "discover valid slugs via resources(type='question')", r"team_pulse_resources\(type='question'\)"),
        (
            "SUB-8",
            "use data.id, or strip the prefix off the list-envelope id",
            r"data\.id \(or strip the prefix\s+off the list-envelope id\)",
        ),
        (
            "SUB-9",
            "user_id is the person's github username",
            r"user_id: the github username of the person the answer is about",
        ),
        ("SUB-10", "recorded as a github-namespaced identity", r"github-namespaced identity"),
        (
            "SUB-11",
            "the API stores it verbatim, resolving to a member at read time",
            r"stores it verbatim,\s+resolving to a team member at read time",
        ),
        ("SUB-12", "metadata is an optional opaque bag", r"metadata: optional opaque bag"),
        (
            "SUB-13",
            "provenance/timing/other context live INSIDE metadata",
            r"source_session_ids\),\s+timing, and any other context live INSIDE it",
        ),
        (
            "SUB-14",
            "generated_at is the ISO-8601 generation timestamp",
            r"generated_at: ISO-8601 timestamp of when the answer was generated",
        ),
    ],
    "team_pulse_status": [
        ("ST-1", "reports THIS client's locally-resolved config", r"THIS client's locally-resolved config"),
        ("ST-2", "no network call", r"no network call"),
        ("ST-3", "no secrets", r"no secrets"),
        ("ST-4", "base_url is the endpoint you point at", r"base_url \(the team-pulse endpoint you point at\)"),
        ("ST-5", "auth_mode is 'key' or 'az'", r"auth_mode \('key' \| 'az'\)"),
        ("ST-6", "credential_type", r"credential_type"),
        ("ST-7", "api_app_id", r"api_app_id"),
        ("ST-8", "forced", r"forced"),
        ("ST-9", "resolved", r"resolved"),
        (
            "ST-10",
            "az_identity_hint is the raw Azure AD token claim, e.g. upn",
            r"az_identity_hint \(raw Azure\s+AD token claim, e\.g\. upn",
        ),
        ("ST-11", "decoded client-side", r"decoded client-side"),
        ("ST-12", "signature NOT verified", r"signature NOT verified"),
        ("ST-13", "None in key mode", r"None in key mode"),
        (
            "ST-14",
            "the hint is not team-pulse's resolved identity and may not match",
            r"NOT team-pulse's resolved identity and may\s+not match it",
        ),
        (
            "ST-15",
            "whoami gives the server-verified member record",
            r"team_pulse_whoami gives the server-verified team member record\s+\(handle/member_id\)",
        ),
        (
            "ST-16",
            "answers which server / how am I authenticating",
            r"which server am I talking to, how am I\s+authenticating\?",
        ),
        (
            "ST-17",
            "works when auth is broken or the server is unreachable",
            r"auth is broken or the server is unreachable",
        ),
        ("ST-18", "use it to diagnose auth/connection failures", r"[Dd]iagnose auth/connection failures"),
        (
            "ST-19",
            "info covers the SERVER's documented capabilities and endpoints",
            r"team_pulse_info the SERVER's documented capabilities and\s+endpoints",
        ),
    ],
    "team_pulse_configure": [
        ("CFG-1", "sets and persists the endpoint URL for this user", r"persists it for this\s+user"),
        (
            "CFG-2",
            "saved to the team-pulse config path (or the env-dir override)",
            r"~/\.amplifier/team-pulse/config\.yaml \(or\s+\$AMPLIFIER_TEAM_PULSE_DIR/config\.yaml\)",
        ),
        (
            "CFG-3",
            "call it when the user provides their URL",
            r"[Cc]all when the user gives their team-pulse endpoint URL",
        ),
        ("CFG-4", "the data tools then work immediately", r"data tools then work\s+immediately"),
        ("CFG-5", "no restart needed", r"no restart"),
        ("CFG-6", "client_id is optional", r"client_id: optional"),
        ("CFG-7", "set client_id only to override the built-in default", r"only to override the built-in\s+default"),
        ("CFG-8", "this bundle prefers Azure AD (bearer) auth", r"prefers Azure AD \(bearer\) auth"),
        (
            "CFG-9",
            "already az login'd: the URL save is the entire setup, no key needed",
            r"already az login'd\s+means the URL save is the entire setup, no key needed",
        ),
        ("CFG-10", "no key parameter by design", r"no key\s+parameter by design"),
        (
            "CFG-11",
            "a shared API key is for automation/service where bearer isn't viable",
            r"automation/service scenarios where\s+bearer isn't viable",
        ),
        ("CFG-12", "the key is set via AMPLIFIER_TEAM_PULSE_KEY", r"AMPLIFIER_TEAM_PULSE_KEY"),
        ("CFG-13", "the key takes precedence over az when both are present", r"beats az when both\s+are present"),
        ("CFG-14", "so set one only if you specifically need it", r"set one only if you specifically need it"),
    ],
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- tests ------------------------------------------------------------------


def test_surface_is_the_expected_twelve_tools() -> None:
    """The head surface is exactly 12 named tools -- no silent additions."""
    assert len(DESCRIPTIONS) == EXPECTED_TOOL_COUNT
    assert set(DESCRIPTIONS) == set(DESCRIPTION_SHA256)
    assert set(DESCRIPTIONS) == set(SEMANTICS)


@pytest.mark.parametrize("tool", sorted(DESCRIPTION_SHA256))
def test_description_bytes_are_pinned(tool: str) -> None:
    """A description cannot drift without a deliberate re-pin."""
    assert _sha(DESCRIPTIONS[tool]) == DESCRIPTION_SHA256[tool], (
        f"{tool} description changed. If intentional, re-pin its SHA-256 to "
        f"{_sha(DESCRIPTIONS[tool])} and update SEMANTICS if any semantic moved."
    )


@pytest.mark.parametrize("tool", sorted(PRESERVED_BYTE_FOR_BYTE))
def test_already_compliant_descriptions_are_preserved_byte_for_byte(tool: str) -> None:
    """These three were already trigger-first and tight; the lean left them alone."""
    assert _sha(DESCRIPTIONS[tool]) == PRESERVED_BYTE_FOR_BYTE[tool]


def test_no_semantic_is_absent() -> None:
    """Every pre-lean semantic still appears in the leaned description.

    This is the fidelity table as an executable check: the expected count of
    absent semantics is 0, and any absence is reported by id, not just counted.
    """
    absent: list[str] = []
    for tool, rows in sorted(SEMANTICS.items()):
        text = DESCRIPTIONS[tool]
        for sid, label, probe in rows:
            if not re.search(probe, text, re.IGNORECASE | re.DOTALL):
                absent.append(f"{sid} ({tool}): {label}  [probe: {probe!r}]")
    assert not absent, "semantics dropped from the leaned surface:\n  " + "\n  ".join(absent)


def test_semantic_inventory_is_not_silently_empty() -> None:
    """Guard the guard: an empty inventory would make the fidelity test vacuous."""
    for tool, rows in SEMANTICS.items():
        assert rows, f"{tool} has no semantic rows -- the fidelity check would be vacuous"
        ids = [sid for sid, _, _ in rows]
        assert len(ids) == len(set(ids)), f"{tool} has duplicate semantic ids"


@pytest.mark.parametrize("tool", sorted(DESCRIPTIONS))
def test_no_example_or_commentary_blocks(tool: str) -> None:
    """``<example>``/``<commentary>`` belong in agent definitions, not tool descriptions."""
    text = DESCRIPTIONS[tool]
    assert "<example>" not in text
    assert "<commentary>" not in text


@pytest.mark.parametrize("tool", sorted(DESCRIPTIONS))
def test_length_cap(tool: str) -> None:
    """Descriptions stay under the cap unless they carry a named contract."""
    n = len(DESCRIPTIONS[tool])
    if tool in CAP_EXEMPT:
        assert n > LENGTH_CAP, (
            f"{tool} is {n} chars, now under the {LENGTH_CAP} cap -- drop its "
            f"CAP_EXEMPT entry rather than carry a stale exemption."
        )
        return
    assert n <= LENGTH_CAP, f"{tool} description is {n} chars, over the {LENGTH_CAP} cap"


@pytest.mark.parametrize("tool", sorted(DESCRIPTIONS))
def test_first_sentence_is_the_trigger(tool: str) -> None:
    """Trigger-first: the opening clause names the tool's job, not a caveat."""
    first = DESCRIPTIONS[tool].split(".")[0].strip()
    assert first, f"{tool} has an empty first sentence"
    assert not first.lower().startswith(("note", "warning", "caution", "important")), (
        f"{tool} opens with a caveat marker rather than its trigger: {first!r}"
    )
