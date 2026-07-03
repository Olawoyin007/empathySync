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

## What the design protects

- **Privacy by locality.** Conversations, patterns, and trusted-network data never leave the
  machine. There are no analytics, accounts, or outbound calls beyond local inference.
- **Restraint that cannot be removed by a prompt.** Crisis routing, harmful-content refusal,
  turn limits, and dependency cooldowns are pipeline steps that execute in code before the
  model is called. A jailbreak or instruction in the user's message cannot disable them. This
  holds for the software as distributed (see *Source modification* below).
- **A crisis floor that does not depend on the model.** Crisis detection has a keyword
  fast-path (`scenarios/classification/llm_classifier.yaml`, `fast_path_crisis`) that runs
  without the LLM, so the highest-priority safety signal still fires when the model is weak,
  slow, or unavailable.
- **Classifier prompt-injection resistance.** User content sent to the LLM classifier is
  wrapped in an explicit `<user_message>...</user_message>` boundary and truncated to a
  maximum length (`src/models/llm_classifier.py`), so untrusted text is treated as data, not
  as instructions to the classifier.

## Engineering controls

The protections above are enforced in code at the locations below. This table is
the quick index for reviewers: a change that weakens one of these is a regression,
not a refactor. The prose above explains *why* each control exists; this maps
*where* it lives.

| Control | Enforcement | Where |
|---------|-------------|-------|
| No external calls | Only outbound traffic is to the local `OLLAMA_HOST` | `src/models/llm_classifier.py`, `src/utils/http_client.py` |
| Prompt-injection boundary | User message wrapped in `<user_message>` tags, truncated to 5000 chars | `src/models/llm_classifier.py` |
| Mid-stream output voice check | 200-char rolling buffer scanned for manipulative-language patterns (false intimacy, dependency-encouraging phrasing, `safe_alternatives.yaml`) before tokens reach the UI. Not a dangerous-content scanner - blocking harmful *requests* is the input-side layers' job | `src/models/ai_wellness_guide.py` |
| No SQL injection via dynamic names | Table and column whitelists; all values parameterized | `src/utils/storage_backend.py` |
| Write gate | `_ensure_write_allowed()` at the top of every write method | `src/utils/write_gate.py`, `src/utils/storage_backend.py` |
| Atomic writes | `mkstemp` + `fsync` + `os.replace` (no torn files on crash) | `src/utils/storage_backend.py` |
| `OLLAMA_HOST` validation | http(s) scheme checked at config load | `src/config/settings.py` |
| Non-root container | `gosu` drops root to `PUID:PGID`; Ollama bound to `127.0.0.1` | `docker/entrypoint.sh`, `docker-compose.yml` |
| Restraint-memory invariant | Property test serializes every persisted structure (both backends) and fails the build if any field outside the allowlist is written - no conversation content, no preference/persona data, ever | `tests/test_restraint_memory.py`, `scenarios/config/system_defaults.yaml` (`restraint_memory`) |

## Known gaps

These are open and acknowledged. Contributor help is welcome.

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
- **No encryption at rest.** Conversation history and tracked patterns are stored as plain
  JSON or SQLite under `data/` (git-ignored). Their confidentiality equals your operating
  system account and file permissions. On a shared or portable device, use full-disk
  encryption. Retention defaults prune conversation history after 30 days and other records
  after 90 (`CONVERSATION_RETENTION_DAYS`, `DATA_RETENTION_DAYS`; set to 0 to disable).
- **No access control.** The optional device lock (`ENABLE_DEVICE_LOCK`) prevents two devices
  writing to synced data at once. It is a data-integrity safeguard, not authentication. Anyone
  with access to the running app or the `data/` directory can read and write everything.
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
