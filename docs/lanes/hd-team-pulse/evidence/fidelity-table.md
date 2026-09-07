| # | Tool | Semantic (from the pre-lean description) | Present after lean |
|---|---|---|---|
| ASK-1 | `team_pulse_ask` | ask is server-side ONLINE GENERATION | YES |
| ASK-2 | `team_pulse_ask` | a Team Pulse LLM composes a bounded answer over current team data | YES |
| ASK-3 | `team_pulse_ask` | prefer the read tools by default | YES |
| ASK-4 | `team_pulse_ask` | names the four read tools | YES |
| ASK-5 | `team_pulse_ask` | read the corpus and compose the answer yourself | YES |
| ASK-6 | `team_pulse_ask` | the read tools are cheaper | YES |
| ASK-7 | `team_pulse_ask` | the read tools return full-fidelity data | YES |
| ASK-8 | `team_pulse_ask` | you are already an LLM that can synthesize from raw reads | YES |
| ASK-9 | `team_pulse_ask` | call ONLY on explicit user direction | YES |
| CFG-1 | `team_pulse_configure` | sets and persists the endpoint URL for this user | YES |
| CFG-2 | `team_pulse_configure` | saved to the team-pulse config path (or the env-dir override) | YES |
| CFG-3 | `team_pulse_configure` | call it when the user provides their URL | YES |
| CFG-4 | `team_pulse_configure` | the data tools then work immediately | YES |
| CFG-5 | `team_pulse_configure` | no restart needed | YES |
| CFG-6 | `team_pulse_configure` | client_id is optional | YES |
| CFG-7 | `team_pulse_configure` | set client_id only to override the built-in default | YES |
| CFG-8 | `team_pulse_configure` | this bundle prefers Azure AD (bearer) auth | YES |
| CFG-9 | `team_pulse_configure` | already az login'd: the URL save is the entire setup, no key needed | YES |
| CFG-10 | `team_pulse_configure` | no key parameter by design | YES |
| CFG-11 | `team_pulse_configure` | a shared API key is for automation/service where bearer isn't viable | YES |
| CFG-12 | `team_pulse_configure` | the key is set via AMPLIFIER_TEAM_PULSE_KEY | YES |
| CFG-13 | `team_pulse_configure` | the key takes precedence over az when both are present | YES |
| CFG-14 | `team_pulse_configure` | so set one only if you specifically need it | YES |
| DL-1 | `team_pulse_download_corpus` | bulk-download the whole mined corpus | YES |
| DL-2 | `team_pulse_download_corpus` | every sub-corpus the server exposes | YES |
| DL-3 | `team_pulse_download_corpus` | to a LOCAL DIRECTORY | YES |
| DL-4 | `team_pulse_download_corpus` | for your own agents / embeddings / grep, offline | YES |
| DL-5 | `team_pulse_download_corpus` | one zip fetch | YES |
| DL-6 | `team_pulse_download_corpus` | extracts the .md tree under dest_dir | YES |
| DL-7 | `team_pulse_download_corpus` | returns the SUMMARY shape | YES |
| DL-8 | `team_pulse_download_corpus` | NOT the page bodies | YES |
| DL-9 | `team_pulse_download_corpus` | because hundreds of docs would crash the session | YES |
| DL-10 | `team_pulse_download_corpus` | this is the offline BULK path | YES |
| DL-11 | `team_pulse_download_corpus` | in-session Q&A goes to search/get | YES |
| DL-12 | `team_pulse_download_corpus` | requires per-user BEARER (az) auth | YES |
| DL-13 | `team_pulse_download_corpus` | a shared API key is refused with 403 | YES |
| DL-14 | `team_pulse_download_corpus` | because a bulk pull must be attributable to a member | YES |
| DL-15 | `team_pulse_download_corpus` | optional folder narrows to ONE sub-corpus | YES |
| DL-16 | `team_pulse_download_corpus` | sub-corpus names are instance-specific | YES |
| DL-17 | `team_pulse_download_corpus` | discover them from info(); never assume | YES |
| GET-1 | `team_pulse_get` | fetch a single resource by full ID | YES |
| GET-2 | `team_pulse_get` | returns the resource envelope shape | YES |
| GET-3 | `team_pulse_get` | ID shape is <type>/<slug> with examples | YES |
| GET-4 | `team_pulse_get` | types are server-defined; see info's resource_types | YES |
| GET-5 | `team_pulse_get` | 404 envelope if unknown | YES |
| GRPH-1 | `team_pulse_graph` | full composed entity graph | YES |
| GRPH-2 | `team_pulse_graph` | every resource of every type | YES |
| GRPH-3 | `team_pulse_graph` | plus computed reverse edges | YES |
| GRPH-4 | `team_pulse_graph` | in one response | YES |
| GRPH-5 | `team_pulse_graph` | large payload | YES |
| GRPH-6 | `team_pulse_graph` | prefer resources/get for targeted lookups | YES |
| GRPH-7 | `team_pulse_graph` | use for cross-resource relationships | YES |
| GRPH-8 | `team_pulse_graph` | worked examples of those relationships | YES |
| INFO-1 | `team_pulse_info` | describes the SERVER, not the client | YES |
| INFO-2 | `team_pulse_info` | remote: needs network and working auth | YES |
| INFO-3 | `team_pulse_info` | returns API name/version | YES |
| INFO-4 | `team_pulse_info` | returns the auth scheme the server documents | YES |
| INFO-5 | `team_pulse_info` | returns capabilities | YES |
| INFO-6 | `team_pulse_info` | returns the endpoint catalog | YES |
| INFO-7 | `team_pulse_info` | returns content collections | YES |
| INFO-8 | `team_pulse_info` | use it to discover what the API exposes | YES |
| INFO-9 | `team_pulse_info` | does NOT report your URL or how you authenticated | YES |
| INFO-10 | `team_pulse_info` | client's resolved config is team_pulse_status | YES |
| PFX-1 | `team_pulse_prefix` | lists resources whose ID starts with a prefix | YES |
| PFX-2 | `team_pulse_prefix` | worked example | YES |
| PFX-3 | `team_pulse_prefix` | cheaper/more precise than search for hierarchy | YES |
| RES-1 | `team_pulse_resources` | lists team-pulse resources | YES |
| RES-2 | `team_pulse_resources` | returns the list envelope shape | YES |
| RES-3 | `team_pulse_resources` | type narrows to one resource class | YES |
| RES-4 | `team_pulse_resources` | valid types are server-defined and vary by deployment | YES |
| RES-5 | `team_pulse_resources` | check team_pulse_info()'s resource_types first | YES |
| RES-6 | `team_pulse_resources` | unsupported type returns HTTP 400 | YES |
| RES-7 | `team_pulse_resources` | status selects lifecycle state for type=question | YES |
| RES-8 | `team_pulse_resources` | default active hides archived | YES |
| RES-9 | `team_pulse_resources` | collection lists a content collection folder | YES |
| SRCH-1 | `team_pulse_search` | naive text search across all resources | YES |
| SRCH-2 | `team_pulse_search` | same list envelope as team_pulse_resources | YES |
| SRCH-3 | `team_pulse_search` | default limit 50, max 200 | YES |
| SRCH-4 | `team_pulse_search` | search is substring-matchy | YES |
| SRCH-5 | `team_pulse_search` | prefer get/prefix for precise ID lookups | YES |
| ST-1 | `team_pulse_status` | reports THIS client's locally-resolved config | YES |
| ST-2 | `team_pulse_status` | no network call | YES |
| ST-3 | `team_pulse_status` | no secrets | YES |
| ST-4 | `team_pulse_status` | base_url is the endpoint you point at | YES |
| ST-5 | `team_pulse_status` | auth_mode is 'key' or 'az' | YES |
| ST-6 | `team_pulse_status` | credential_type | YES |
| ST-7 | `team_pulse_status` | api_app_id | YES |
| ST-8 | `team_pulse_status` | forced | YES |
| ST-9 | `team_pulse_status` | resolved | YES |
| ST-10 | `team_pulse_status` | az_identity_hint is the raw Azure AD token claim, e.g. upn | YES |
| ST-11 | `team_pulse_status` | decoded client-side | YES |
| ST-12 | `team_pulse_status` | signature NOT verified | YES |
| ST-13 | `team_pulse_status` | None in key mode | YES |
| ST-14 | `team_pulse_status` | the hint is not team-pulse's resolved identity and may not match | YES |
| ST-15 | `team_pulse_status` | whoami gives the server-verified member record | YES |
| ST-16 | `team_pulse_status` | answers which server / how am I authenticating | YES |
| ST-17 | `team_pulse_status` | works when auth is broken or the server is unreachable | YES |
| ST-18 | `team_pulse_status` | use it to diagnose auth/connection failures | YES |
| ST-19 | `team_pulse_status` | info covers the SERVER's documented capabilities and endpoints | YES |
| SUB-1 | `team_pulse_submit_answer` | submit a session-mined answer to a reflection question | YES |
| SUB-2 | `team_pulse_submit_answer` | records an AI-generated answer attributed to a specific user | YES |
| SUB-3 | `team_pulse_submit_answer` | synthesized from their Context Intelligence sessions | YES |
| SUB-4 | `team_pulse_submit_answer` | question_id is the BARE SLUG, with an example | YES |
| SUB-5 | `team_pulse_submit_answer` | NOT the hierarchical questions/<slug> form | YES |
| SUB-6 | `team_pulse_submit_answer` | strip the prefix if you have it | YES |
| SUB-7 | `team_pulse_submit_answer` | discover valid slugs via resources(type='question') | YES |
| SUB-8 | `team_pulse_submit_answer` | use data.id, or strip the prefix off the list-envelope id | YES |
| SUB-9 | `team_pulse_submit_answer` | user_id is the person's github username | YES |
| SUB-10 | `team_pulse_submit_answer` | recorded as a github-namespaced identity | YES |
| SUB-11 | `team_pulse_submit_answer` | the API stores it verbatim, resolving to a member at read time | YES |
| SUB-12 | `team_pulse_submit_answer` | metadata is an optional opaque bag | YES |
| SUB-13 | `team_pulse_submit_answer` | provenance/timing/other context live INSIDE metadata | YES |
| SUB-14 | `team_pulse_submit_answer` | generated_at is the ISO-8601 generation timestamp | YES |
| WHO-1 | `team_pulse_whoami` | resolves the current caller's identity | YES |
| WHO-2 | `team_pulse_whoami` | for me/my/mine phrasing | YES |
| WHO-3 | `team_pulse_whoami` | worked examples of that phrasing | YES |
| WHO-4 | `team_pulse_whoami` | takes no input | YES |
| WHO-5 | `team_pulse_whoami` | returns how the caller authenticated | YES |
| WHO-6 | `team_pulse_whoami` | returns whether a per-user identity is available | YES |
| WHO-7 | `team_pulse_whoami` | SERVER-verified identity (handle/member_id) | YES |
| WHO-8 | `team_pulse_whoami` | distinct from status's az_identity_hint | YES |
| WHO-9 | `team_pulse_whoami` | that hint is a raw, unverified Azure token claim | YES |
| WHO-10 | `team_pulse_whoami` | and may not match | YES |

**Total semantics: 123. Present: 123. Absent: 0 (expected 0).**
