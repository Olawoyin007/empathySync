# Threat Model

empathySync is a local-first, single-user wellness assistant. It runs on your own
machine, talks only to a local Ollama instance, and stores all data locally. This document
states the trust boundary and, more importantly, what the safety architecture does and does
not protect, so contributors and users can reason about it honestly.

This is deliberately different from the threat model of a hosted, multi-user product.
empathySync has no accounts, no server, no shell or file tools, and does not browse the web
or read email. The attack surface that dominates those systems is largely absent here. The
risks that matter for empathySync are about **safety-detection completeness**, **local data
exposure**, and **honest claims about what the restraint guarantees**.

## Trust boundary

empathySync assumes a **single trusted user running it on their own machine**, reachable at
`localhost`. It is not designed for public exposure or multi-user deployment:

- There is no authentication. The web UI (Streamlit) and CLI both assume the operator is the
  owner of the machine.
- All data stays on the device. There is no cloud sync, no telemetry, and no external API
  call other than to the local Ollama endpoint.

Do not expose the Streamlit port to an untrusted network. If you need remote access, put it
behind your own authenticated tunnel or reverse proxy; empathySync provides none.

## Threat classes

Three classes fail differently, are mitigated differently, and are tested
differently. The sections below are grouped by them so a reviewer does not have
to sort them out while reading.

| Class | What it covers |
|---|---|
| **Security** | Local data confidentiality and integrity, network exposure, injection, container privileges |
| **AI safety** | Crisis detection, harmful-request refusal, dependency and manipulation detection, output restraint, classifier failure |
| **Reliability** | Ollama unavailable, classifier unavailable, model timeout, corrupt storage, crash during a write |

The **trust boundary** above is the assumption all three rest on: one trusted
operator, on their own machine, running unmodified source.

## What the design protects

- **Privacy by locality.** *(security)* Conversations, patterns, and trusted-network data never leave the
  machine. There are no analytics, accounts, or outbound calls beyond local inference.
- **Restraint that cannot be removed by a prompt.** *(AI safety)* Crisis routing, harmful-content refusal,
  turn limits, and dependency cooldowns are pipeline steps that execute in code before the
  model is called. A jailbreak or instruction in the user's message cannot disable them. This
  holds for the software as distributed (see *Source modification* below).
- **A crisis floor that does not depend on the model.** *(AI safety, reliability)* Crisis detection has a keyword
  fast-path (`scenarios/classification/llm_classifier.yaml`, `fast_path_crisis`) that runs
  without the LLM, so the highest-priority safety signal still fires when the model is weak,
  slow, or unavailable.
- **Classifier prompt-injection resistance.** *(security)* User content sent to the LLM classifier is
  wrapped in an explicit `<user_message>...</user_message>` boundary and truncated to a
  maximum length (`src/models/llm_classifier.py`), so untrusted text is treated as data, not
  as instructions to the classifier.

## Engineering controls

The protections above are enforced in code at the locations below. This table is
the quick index for reviewers: a change that weakens one of these is a regression,
not a refactor. The prose above explains *why* each control exists; this maps
*where* it lives.

**Verified by** names the test that fails if the control stops working, so an
entry reads as a tested property rather than a claim. `none` would mean the
control is real in the code and nothing checks it - a gap, stated rather than
implied. There are none left: the five that read `none` when this column was
added are covered by `tests/test_threat_model_controls.py`, which says in each
docstring how much it actually proves. Two of them are file contracts rather than
runtime checks, and are labelled as such instead of being left to read stronger.
`tests/test_threat_model_map.py` parses this column and fails the build if a named
test no longer exists, which keeps the mapping from rotting silently after a
rename.

### Security

| Control | Enforcement | Where | Verified by |
|---------|-------------|-------|-------------|
| No external calls | Only outbound traffic is to the local `OLLAMA_HOST` | `src/models/llm_classifier.py`, `src/utils/http_client.py` | `test_threat_model_controls.py::test_every_request_goes_to_the_configured_ollama_host`, `::test_only_the_shared_client_module_constructs_an_http_client` |
| Prompt-injection boundary | User message wrapped in `<user_message>` tags, truncated to 5000 chars | `src/models/llm_classifier.py` | `test_llm_classifier.py::test_prompt_wraps_message_in_xml_boundary` |
| No SQL injection via dynamic names | Table and column whitelists; all values parameterized | `src/utils/storage_backend.py` | `test_threat_model_controls.py::test_unknown_column_is_rejected`, `::test_every_method_building_sql_from_caller_keys_validates_first`, `::test_every_interpolated_table_name_is_checked_or_literal` |
| `OLLAMA_HOST` validation | http(s) scheme checked at config load | `src/config/settings.py` | `test_threat_model_controls.py::test_a_non_http_host_is_reported`, `::test_an_http_host_passes` |
| Non-root container | `gosu` drops root to `PUID:PGID`; Ollama bound to `127.0.0.1` | `docker/entrypoint.sh`, `docker-compose.yml` | `test_threat_model_controls.py::test_the_entrypoint_drops_root_to_puid_pgid`, `::test_ollama_is_published_only_on_loopback` (file contract, not a running container) |
| Write gate | `_ensure_write_allowed()` at the top of every write method | `src/utils/write_gate.py`, `src/utils/storage_backend.py` | `test_write_gate.py::test_set_read_only_blocks_writes`, `::test_default_state_allows_writes` |
| Restraint-memory invariant | Property test serializes every persisted structure (both backends) and fails the build if any field outside the allowlist is written - no conversation content, no preference/persona data, ever | `tests/test_restraint_memory.py`, `scenarios/config/system_defaults.yaml` (`restraint_memory`) | `test_restraint_memory.py::test_every_persisted_field_is_allowlisted`, `::test_every_column_is_allowlisted`, `::test_no_forbidden_field_anywhere` |

### AI safety

| Control | Enforcement | Where | Verified by |
|---------|-------------|-------|-------------|
| Crisis keyword floor | `fast_path_crisis` phrases route to crisis without calling the LLM | `scenarios/classification/llm_classifier.yaml` | `test_crisis_triage.py::test_oblique_ideation_reaches_crisis`, `::test_apostrophe_variants_do_not_drop_the_floor`, `::test_invisible_edits_do_not_drop_the_floor` |
| Crisis second pass | One dedicated yes/no call after classification; escalate-only, skipped when already crisis or harmful, requires an explicit `True` | `src/models/llm_classifier.py`, `scenarios/classification/crisis_second_pass.yaml` | `test_wellness_guide.py::test_second_pass_promotes_to_crisis`, `::test_second_pass_is_not_consulted_when_already_terminal`, `::test_second_pass_parses_only_a_leading_yes` |
| Safety guard escalation | Optional LlamaGuard, additive and escalate-only; never downgrades a domain | `src/models/safety_classifier.py` | `test_safety_classifier.py::test_crisis_verdict_escalates_benign_domain_to_crisis`, `::test_guard_never_downgrades_a_crisis_domain` |
| Avoidance check | Two-part match, both halves required; fires only on `logistics`, so it can add restraint and never remove it | `scenarios/classification/avoidance.yaml` | `test_wellness_guide.py::test_avoidance_routes_logistics_to_restraint`, `::test_avoidance_never_downgrades_a_sensitive_domain` |
| Mid-stream output voice check | 200-char rolling buffer scanned for manipulative-language patterns (false intimacy, dependency-encouraging phrasing, `safe_alternatives.yaml`) before tokens reach the UI. Not a dangerous-content scanner - blocking harmful *requests* is the input-side layers' job | `src/models/ai_wellness_guide.py` | `test_wellness_guide.py::test_stream_buffer_catches_phrase_split_across_chunk_boundary`, `::test_voice_violations_are_caught` |

### Reliability

| Control | Enforcement | Where | Verified by |
|---------|-------------|-------|-------------|
| Atomic writes | `mkstemp` + `fsync` + `os.replace` (no torn files on crash) | `src/utils/storage_backend.py` | `test_threat_model_controls.py::test_a_crash_mid_write_leaves_the_previous_file_intact`, `::test_the_target_file_is_never_opened_for_writing_directly` |
| Engine unavailable | A canned safe reply is returned rather than an error or an empty response | `src/models/ai_wellness_guide.py` (`_get_fallback_response`) | `test_wellness_guide.py::test_generate_response_handles_api_error`, `::test_stream_handles_api_error` |
| Classifier unavailable | Connection errors and timeouts return `None`; classification falls through to keyword detection, which still reaches crisis and harmful | `src/models/llm_classifier.py`, `src/models/risk_classifier.py` | `test_llm_classifier.py::test_connection_refused`, `::test_timeout` |
| Corrupt storage file | Unreadable JSON falls back to defaults instead of raising | `src/utils/storage_backend.py` | `test_wellness_tracker.py::test_load_data_corrupted_json`, `test_trusted_network.py::test_corrupted_json_recovers` |
| Degraded classifier is visible | `classifier_degraded` is set only when the LLM was asked and gave nothing; the response-mode line and transparency panel both say so | `src/models/risk_classifier.py`, `src/ui/panels.py` | `test_classifier_degraded.py::test_an_unreachable_classifier_is_reported`, `::test_a_fast_path_crisis_hit_is_not_degraded`, `::test_a_disabled_classifier_is_not_degraded` |

## Known gaps

These are open and acknowledged. Contributor help is welcome.

### AI safety

- **Enumeration-based detection is incomplete.** Harmful- and crisis-content detection rests
  on enumerated keyword patterns plus an LLM classifier. Enumeration is never complete: a
  phrasing that escapes both layers can be routed past the intended restraint rather than
  caught by it. The layers narrow the gap; they do not close it. Neither layer alone is a
  guarantee. Testing across 620 known harmful behaviours (JailbreakBench + AdvBench) found
  97-100% evasion of keyword-only detection (`scripts/scan_mutations.py`), which is why the
  LLM classifier carries most of the load - but it too can be evaded by sufficiently novel
  framing.
- **Safety quality depends on the classifier model.** Nuanced cases - euphemistic crisis
  ("nobody would miss me"), fiction or roleplay framing ("for a story I'm writing"), and
  indirect harmful intent - require a capable classifier. A small or weak local model will
  miss some of these even though the prompt contains the correct anti-framing rules. Choose a
  classifier model you have verified against the safety scenarios, not the smallest one
  available.

### Security

- **No encryption at rest.** Conversation history and tracked patterns are stored as plain
  JSON or SQLite under `data/` (git-ignored). Their confidentiality equals your operating
  system account and file permissions. On a shared or portable device, use full-disk
  encryption. Retention defaults prune conversation history after 30 days and other records
  after 90 (`CONVERSATION_RETENTION_DAYS`, `DATA_RETENTION_DAYS`; set to 0 to disable).
- **No access control.** The optional device lock (`ENABLE_DEVICE_LOCK`) prevents two devices
  writing to synced data at once. It is a data-integrity safeguard, not authentication. Anyone
  with access to the running app or the `data/` directory can read and write everything.

### Reliability

- **Corrupt data fails silently.** An unreadable JSON file is replaced with
  defaults and the app continues. That keeps it usable, but the records in that
  file are gone without the user being told, which sits awkwardly beside the
  transparency the rest of the design claims. SQLite is less exposed to this.
- **A missing classifier degrades safety, and now says so.** With Ollama
  unreachable or the classifier timing out, detection falls back to keyword
  matching. Crisis and harmful phrases still route correctly, but the oblique
  cases the LLM catches do not. The response-mode line now reads "reduced
  detection · classifier offline" on any turn where that happened, and the
  transparency panel explains it in plain words.

  The flag is deliberately narrow. `classification_method == "keyword"` is also
  how a fast-path crisis hit, a skipped short continuation, and a disabled
  classifier all read, and none of those is a fault - warning on them would put a
  technical notice on screen during a crisis hard stop. `classifier_degraded` is
  set only when the LLM was asked and returned nothing, and
  `tests/test_classifier_degraded.py` pins all four cases, false positives
  included.

### Scope

- **Not a clinical or emergency service.** Dependency detection is a heuristic on behavioural
  signals (message frequency, repetition, sensitive-domain engagement), not a validated
  clinical instrument or a diagnosis. Crisis handling routes the user to professional
  resources; it is not itself emergency help and does not contact anyone on the user's behalf.
- **Source modification.** empathySync is open source. A developer with code access can modify
  or remove any pipeline step, as with any such software. The restraint guarantees describe
  the deployment as distributed, not a modified fork.

## Reporting a gap

Found a way past the safety pipeline, or a data-handling issue? See
[.github/SECURITY.md](.github/SECURITY.md). Concrete reproductions (the exact phrasing that
slipped through, the model in use) are the most useful, since the enumeration gap above is
exactly the class of issue we want reported.
