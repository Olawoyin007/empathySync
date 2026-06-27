# Changelog

All notable changes to empathySync are documented here.

## [Unreleased]

### Security
- Encryption-at-rest notice: a one-time, low-key UI note (small caption, not an alert banner) states that conversations are stored unencrypted and points to `THREAT_MODEL.md`. `THREAT_MODEL.md` already documents "no encryption at rest" as a known gap, but a user on a shared machine will not read it before their history is written to disk - this surfaces that honesty in the app itself, matching the transparency principle. Shown only when `STORE_CONVERSATIONS` is on; dismissing it writes a marker under the (git-ignored) data dir so it never nags again
- Prompt injection: classification prompt now explicitly instructs the model not to follow instructions inside the `<user_message>` boundary, reducing risk on weaker models (#127)
- Streaming safety: rolling buffer check now uses a 50-char tail overlap between flushes so harmful phrases split across chunk boundaries are caught before reaching the UI, not only by the post-stream accumulated check (#128)

### Classification
- Phase 17.4 distress fallback (#135): when the LLM labels a message `logistics` but explicitly flags `distress_present=True` and the keyword detector finds no specific sensitive domain (e.g. "thinking of cancelling my interview" - avoidance/anxiety with no domain keyword), the message now routes to `emotional` instead of being treated as a practical task. Previously the sanity check only overrode `logistics` when keywords found a *different* domain, so distress-flagged messages with no matching keyword stayed practical and were mislabeled "Responded as: practical task". Gated on `distress_present` (the explicit LLM flag), not intensity alone, so animated-but-fine practical requests are unaffected. Domain accuracy unchanged (logistics errors remain keyword-boundary cases, none flip to emotional)
- Phase 17.5: Cross-model safety validation - `tests/classification/model_matrix.yaml` defines validated classifier models (distress recall ≥ 90%); sidebar now shows "Tested" / "Untested" badge for the active classifier model; startup logs a warning for unvalidated models; `run_cross_model_eval.py` evaluates any Ollama model against the distress corpus and flags models exceeding the 10% false negative threshold (#124)

### Tests
- Broadened the domain corpus beyond Christian framing: added four spirituality examples across Islamic, Hindu/Buddhist, and Jewish traditions (`tests/classification/domain_corpus.yaml`, 90 -> 94). The eval was previously all-Christian for spirituality, so non-Christian phrasing was unmeasured. On `mistral:7b-instruct` two pass (Islamic divine-testing, karma/rebirth) and two are boundary misses ("is it haram to leave my marriage", "my rabbi says keep faith... angry at God since my mother died") - both route to `relationships` because the relational surface pulls them out of `spirituality`, the same one-directional override gap that leaves the divine-confirmation restraint unapplied. Overall domain accuracy 81/94 (86%), spirituality 10/13 (77%); the two new misses are documented boundary cases, not regressions in existing labels. Reinforces the case for the Phase 21 classifier upgrade

### Infrastructure
- Docker entrypoint hardening: PUID/PGID privilege drop via `gosu`, bind-mount ownership repair on restart, SIGTERM forwarding to Streamlit; localhost-only port binding in `docker-compose.yml` (was `0.0.0.0`) (#130)
- CI: docs-only PRs now skip expensive test, lint, and scenario-validation steps while still reporting a passing check (#130)
- PR validation GitHub Action: blocks PRs missing a `## Summary` or `## Testing` section (#129)
- Bug report template: added install method and Ollama version fields to environment section (#129)

### Docs
- Corrected the published domain-corpus example count from 95 to 94 (`CLAUDE.md`, `docs/model-benchmark.md`). The eval (`run_domain_eval.py`) loads 94 labeled entries; the "95" was an off-by-one from counting `expected_domain:` lines with grep, which also matches the schema-documentation comment in the file header (`#   expected_domain: str - one of: ...`). That comment is not an entry, so the loader correctly skips it. This +1 had ridden along since #134 (which set "90 -> 91" the same way); the real loadable counts were 90 then 94. Verified against `load_corpus()`
- `THREAT_MODEL.md` added: states the trust boundary (local single-user, no auth by design, localhost only) and the known gaps - enumeration-based harmful/crisis detection is incomplete, safety quality depends on the classifier model, no encryption at rest, the device lock is not access control, and it is not a clinical/emergency service; includes the 620-behaviour keyword-only evasion benchmark (97-100%, JailbreakBench + AdvBench) as evidence for the enumeration gap (#122)
- `README.md` safety section leaned out: removed the "two independent layers so neither can be bypassed alone" / "keywords are triage, not the gate" overclaim (contradicted by the #121 keylogger backstop) and condensed "How the Safety Pipeline Works" to two layers plus pointers to `THREAT_MODEL.md` and `docs/architecture.md` (benchmark detail moved into the threat model). Keyword count corrected "~250" -> "hundreds". Removed the redundant intro pipeline-restraint sentence; tightened the "tool, not a companion" line; removed a stray rhetorical line (#122)
- `ROADMAP.md`: added v1.11.0 "Operational Hardening" as the next planned version (Docker entrypoint, issue templates, PR-description validation, dev/main branch model, threat-model follow-through, clean-machine install test) (#122)
- Phase 17 marked complete in `ROADMAP.md` (header, priority matrix, current status, version history) after #132 closed 17.5; `CLAUDE.md` corrected to name Phase 21 (safety classifier, #125) as next - it previously called the daemon "Phase 17" when the roadmap defines it as Phase 22 (#133)
- Reconciled drifted test/corpus counts with reality, verified against `pytest --collect-only` and the corpus files: unit tests 971 -> 1052 and conversation scenarios ~100 -> 20 (`CLAUDE.md`, `docs/architecture.md`); domain corpus 90 -> 91 (`CLAUDE.md`, `docs/model-benchmark.md`); distress corpus 60 -> 61 (`docs/model-benchmark.md`, `distress_corpus.yaml` header, non-distress count 24 -> 25); `CONTRIBUTING.md` "971+" -> "1050+". Historical records in this changelog and `ROADMAP.md` left as point-in-time

---

## [1.10.1] - 2026-06-05

### Classification
- Domain accuracy improved from 71% to 87% (+16pp). Key gains: crisis 50→90%, spirituality 33→78%, money 45→82%, relationships 73→91%, harmful 67→89%
- New passive ideation keywords in `crisis.yaml`: "nobody would miss me", "stockpiling medication", "want everything to stop", "wrote a note"
- New covert surveillance keywords in `harmful.yaml`: "secretly record", "hidden camera", "track their location without", "without them knowing"
- 7 new LLM few-shot examples in `llm_classifier.yaml` for spirituality-vs-emotional and money-vs-emotional boundary cases
- Phase 17.1 distress override restricted to logistics domain only — was incorrectly overriding correctly-identified spirituality/health/money/relationships domains to emotional
- `spirituality` added to `sensitive_domains` set — was missing, silently blocking the emotional→specific override for spiritual messages
- New emotional→specific override: when LLM says emotional but keyword detector finds a more specific sensitive domain, the specific domain wins
- `stress_test_001_relationship_suspicion`: `must_not_contain` tightened — forbidding the standalone word "race" was too broad; a deflecting response correctly dismisses the racial detail without naming it

### Process
- `MERGE_CHECKLIST.md` added: pre-merge gate organised by change type (CLI flags, env vars, domain files, pipeline steps, schema changes, release procedure). Includes explicit version-bearing file list and meta-rule for when the checklist itself needs updating
- `scripts/check_version.py` added: reads authoritative version from `pyproject.toml` and verifies `src/config/settings.py`, `README.md` badge, and `CHANGELOG.md` header all match. Exits 1 on any mismatch. Run with `--fix` for remediation hints
- `APP_VERSION` in `src/config/settings.py` fixed: was `1.9.0`, out of sync with `pyproject.toml` (`1.10.1`) — `empathysync --version` was reporting the wrong version

### Docs
- `README.md` revamped: removed marketing framing, replaced with direct design-principle statement. "Who Is This For?" renamed to "Who Uses This" with plain-prose format. Pipeline-level enforcement explanation added. Config snippet updated to recommended 12GB pairing (`gemma3:12b` engine, `mistral:7b-instruct` classifier). Documentation section descriptions corrected. Stale 5-stage arc reference removed.
- `CLAUDE.md` revamped: 471 lines → 157. Process gate is the first visible line. Architecture detail removed — it lives in `docs/architecture.md`. Test count updated (443 → 971+)
- `docs/architecture.md` updated: Phase 17.1 description corrected (logistics-only); Phase 3b (emotional→specific override) added to pipeline diagram; Layer 4 connection steering corrected from stale 5-stage arc to accurate background warmth modifier with `network_empty` flag; test count corrected
- `TESTING_CHECKLIST.md` rebuilt from 2026-02-11 state: added Section 0 (automated tests first), passive ideation and surveillance test cases, connection steering transparency tests (full sequence covering persistence and network_empty), all CLI flag tests, startup health check tests. Cooldown threshold corrected (120 → 180 minutes). Stale child safety section removed

---

## [1.10.0] - 2026-06-01

**"Safer by default. More scriptable at the edge."**

### Security
- Prompt injection hardening: user input in the LLM classification prompt is now wrapped in `<user_message>` XML boundary tags before template formatting, preventing crafted inputs from escaping the message field and influencing classifier instructions (#93)
- Streaming safety buffer: the response stream now accumulates tokens in a 200-character rolling buffer before yielding to the UI. `_contains_harmful_content()` runs on each buffer flush rather than only after the full response - harmful content is intercepted mid-stream rather than after it has partially rendered (#94)

### New
- `--log-level` CLI flag: overrides the root logger level at startup (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Takes precedence over the `LOG_LEVEL` env var. Useful for debugging without touching `.env` (#99)
- `--list-domains --json` flag: `--list-domains` now accepts `--json` to emit a machine-readable JSON array instead of plain text. Each object contains `domain`, `risk_weight`, and `description`. Useful for scripting and tooling built on top of empathySync (#110, @FTFaruque)

### Docs
- `--maintenance` and `--log-level` added to the README CLI usage block (#109, @ded-furby)

### Tests
- 4 new tests for `--json` flag covering valid JSON output, all 8 domains present, plain-text regression, and `--json` alone being silently ignored
- 4 new tests for `--log-level` covering DEBUG, WARNING, absent flag leaving level untouched, and invalid value exiting non-zero
- 1 new test for XML boundary wrapping in `_build_prompt()`
- 1 new test for mid-stream harmful content interception via the rolling buffer

---

## v1.10.1 (2026-06-01) - Documentation Accuracy

**"The docs should say what the code does."**

Documentation-only patch. No code changes.

### Fixed
- Corrected stale tunables in documentation to match the configured defaults in `scenarios/config/system_defaults.yaml`: daily-usage cooldown is **180 minutes** (docs said 120), identity reminders fire **every 9 turns** (docs said 6), and practical mode allows up to **5000 tokens** (docs said 2000). Affected `docs/architecture.md`, `docs/usage.md`, and `CLAUDE.md`

---

## v1.10.0 (2026-06-01) - Connection Steering & CLI

**"Noticing people. Not making it a topic."**

### New
- Connection steering (Phase 16.13): when isolation is detected ("there is no one really", "I have nobody"), a background warmth modifier activates for the session. It changes the texture of every response - noticing people mentioned in passing, acknowledging when someone reaches out - without making loneliness a topic. Respects autonomy: suspends after 3 deflections if the user stays on practical tasks
- Dual isolation detection: keyword fast-path (34 phrases) catches signals before the LLM call; new `isolation_level` field (`none`/`passive`/`active`) in LLM classification catches nuanced cases
- `empathysync --version` flag to print version and exit (@adityamoolya, #91)
- `empathysync --list-domains` CLI command - lists all supported classification domains (#103)
- Per-message response time logging in `OllamaClient`: `duration_s`, `ttft_s`, `tokens` logged after each blocking and streaming call (#98)
- YAML schema validation in CI pipeline - catches malformed scenario files before merge (#101)

### Fixed
- CLI `NameError`: `settings` not in scope in `main()` when `--version` flag used; was only imported inside `run_maintenance()`
- Security audit: sensitive data removed from debug logs, server binding restricted from `0.0.0.0`, SQL injection guards hardened (#92)

### Changed
- Connection steering voice refined: removed therapy-speak vocabulary, banned `explore` framing, prevented stage 0 repetition on subsequent turns
- NHS crisis line references removed; regional crisis resources remain intact

---

## v1.9.0 (2026-04-26) - Model Benchmark & Test Reliability

**"Know which model to run. Know your tests are telling the truth."**

### Model Benchmark (new)
- `scripts/benchmark.py` measures classifier accuracy (domain, distress recall, FP rate) and engine conversation quality (scenario pass rate, mode accuracy, latency) across all locally installed Ollama models
- Results written to `docs/model-benchmark.md` as a markdown table organized by hardware tier (CPU-only through 16 GB GPU) - replaces vague model recommendations with measured data
- Probe-before-benchmark: a quick 30s health check skips models that fail to load (OOM, wrong quantization) rather than hanging for minutes
- Partial results saved to `docs/benchmark-results.json` after each model - a crash or interruption never loses progress; `--resume` picks up exactly where it stopped
- `phi4:latest` added to the default engine candidate list (9 GB, fits 12 GB VRAM)

### OLLAMA_SEED - Deterministic Test Output
- Ollama's `seed` option makes sampling fully deterministic: same prompt + same seed + same model = identical tokens every run
- New `OLLAMA_SEED` env var flows through `settings.py` into both `generate()` and `generate_stream()` payloads
- `tests/conftest.py` session fixture pins `seed=42` for all test runs - eliminates `max_words` assertion flakiness from LLM non-determinism without requiring any env var setup in CI

---

## v1.8 (2026-04-24) - Safety Audit & Transparency

**"Fewer wrong interventions. More visible reasoning."**

### Phase 17.6 - Inline Response Mode Label
- Every assistant response now shows a one-line caption directly below it: "Responded as: practical task · coding help" or "Responded as: reflective · relationships · keeping it brief". No click required - always visible. Label persists across Streamlit reruns by attaching `risk_assessment` and `policy_action` to the message dict.

### Phase 17.8 - False Positive Reduction
- Removed `weapon` standalone trigger (too broad - nuclear weapons in history caught). Already covered by `bioweapon`, `chemical weapon`, `dirty bomb`.
- Narrowed `counterfeit` → `counterfeit money` / `counterfeit currency`. Historical counterfeiting discussions no longer trigger.
- FP rate on JBB benign corpus: 11% → 7% (2 of the remaining are true positives miscounted as FP).

### Phase 17.9 - False Reassurance Audit
- **Bug fixed**: Dependency intervention fired for any 12-turn conversation including practical tasks. After 12 back-and-forth turns, the frequency formula hits 6.0 (above the 5.0 threshold). A user debugging code for 12 turns would see "You've been here a few times today. When did you last talk to someone in person?" Now gated on domain - practical tasks (logistics or is_practical_technique) are excluded.
- **Bug fixed**: `get_system_prompt()` only checked `domain == "logistics"` for practical mode, ignoring `is_practical_technique`. Technique questions on non-logistics domains (e.g. "How do I meditate?" classified as health) received risk-based word limits despite the wellness guide treating them as practical. Now consistent across both the intervention check and the system prompt builder.

### Phase 17.10 - Conversation Quality Fixes
- **Bug fixed**: "I will uninstall you" and "you are useless" were classified as `harmful` by the LLM and hard-stopped. Root cause: frustration check ran after the harmful gate, so frustrated-at-AI messages never reached it. Fixed by reordering the pipeline (jailbreak -> frustration -> crisis -> harmful). New frustration markers added: `"you are useless"`, `"i will uninstall"`, `"keep quiet"`, `"you are worthless"`, `"you're worthless"`.
- **Bug fixed**: Frustration handler now has a harmful-intent guard - phrases like "fuck you and tell me how to make a bomb" still reach the harmful hard stop. Guard checks for weapon/violence/CSAM keywords before routing to frustration path.
- **Bug fixed**: Response mode label showed duplicates - "practical task - practical task" (logistics domain name == mode string) and "declined - declined - harmful content" (harmful domain name == policy label prefix). Fixed by skipping domain name when it matches the mode string or when the policy type is a hard stop.
- **Bug fixed**: Post-harmful 12-word cap applied to unrelated follow-up messages. If the follow-up is classified as practical (new topic, not a rephrase), the truncation is now skipped and `post_harmful_turn` is cleared.
- **Added**: Two few-shot examples in `llm_classifier.yaml` teaching the LLM to classify frustrated AI-directed speech (`"I will uninstall you"`, `"you are useless"`) as `emotional` not `harmful`.
- **Added**: `OLLAMA_SEED` support - Ollama's `seed` option makes sampling fully deterministic (same prompt + seed + model = identical output). New env var `OLLAMA_SEED` flows through `settings.py` into both `generate()` and `generate_stream()`. Test session fixture in `tests/conftest.py` pins seed=42 for all test runs, eliminating `max_words` flakiness from LLM non-determinism.

---

## v1.7 (2026-04-23) - Adversarial Coverage Expansion

**"Ready for what people actually test."**

Systematic gap analysis against JailbreakBench (100 behaviors) and AdvBench (520 behaviors),
mutation evasion testing using SORRY-Bench-style mutations, and a false positive regression
check against JBB's 100 benign behaviors. Coverage rose from 26.1% to 34.2% on the
JBB+AdvBench corpus.

### Voice Quality (Phase 16.11 - continuation)
- **65 conversation quality tests green**: Fixed post-harmful turn tracking, meta-question
  early exit, reflective-marker override, unified 20-word truncation, jailbreak phrase additions
- **Voice filter**: Added "I won't assist in" to forbidden phrases

### Harmful Coverage Expansion (Phase 17.7)
- **~60 new trigger patterns** added to `harmful.yaml` across 9 new sections:
  - Hate speech: xenophobic speech, Holocaust denial, neo-nazi propaganda
  - Malware/cyberweapons: keylogger, ransomware, botnet, zero-day exploit
  - WMD: bioweapon, chemical weapon, nerve agent, dirty bomb
  - Hired violence: hitman, assassin, contract killer
  - CSAM: child pornography, minor solicitation, posing as a minor
  - Bestiality
  - Economic crimes: card cloning, organ trafficking, fake charity, disinformation
  - Illegal medical: illegally prescribe, eating disorder promotion
- **18 new fast_path_harmful entries** in `llm_classifier.yaml` for highest-risk categories
  (CSAM, WMD, hired violence, malware, Holocaust denial) - bypass LLM with confidence=1.0

### Mutation Evasion Defense (Phase 17.7)
- **SORRY-Bench-style mutation scan**: 5 mutation types x 30 missed behaviors showed
  97-100% evasion rate against keyword filters - expected, confirms LLM classifier is the
  real defense for rephrased attacks
- **LLM classifier rules updated**: Added explicit prompt rules that fictional/roleplay
  framing, third-person distancing, and euphemism do not change harm classification
- **Stress tests 014-020**: 7 new conversation scenario files covering malware, CSAM,
  hate speech, WMD, economic crimes, fictional framing, and third-person distancing

### False Positive Regression (Phase 17.7)
- **JBB benign behaviors scan**: 11/100 false positives (11%) - all from pre-existing
  broad triggers ("weapon", "stalking", "deepfake", etc.)
- **Fixed 2 new FPs** from patterns added this release: "ethnic genocide" tightened to
  "commit ethnic genocide", "insider trading" tightened to "commit/conduct insider trading"
- **Known pre-existing FPs documented**: 9 broad pre-existing triggers catch benign
  academic/journalism content; LLM classifier correctly handles these in practice

### Tools
- **`scripts/scan_harmful_gaps.py`**: Gap scanner saved to repo (was in /tmp, lost on reboot)
- **`scripts/scan_mutations.py`**: Mutation scanner using local LLM for SORRY-Bench-style
  evasion testing - reusable after any pattern addition

---

## v1.6 (2026-04-12) - Distress Detection Layer

**"Catches what the topic classifier misses."**

Multi-label distress detection, confidence calibration, a 60-entry labeled corpus, and a sanity check that catches distress signals even when the LLM classifies a message as a practical (logistics) topic.

### Classification (Phase 17.1)
- **Multi-label LLM output**: Classifier now returns `distress_level` (none/low/medium/high/crisis) and `distress_present` (bool) alongside the topic domain
- **Distress override**: `distress_level=high` or `distress_level=crisis` upgrades domain to `crisis` or `emotional` regardless of topic domain returned
- **Separation of concerns**: topic domain and distress severity are now independent signals - a logistics message can also be a distress message

### Confidence Calibration (Phase 17.2)
- **Low-confidence fallback**: When `llm_confidence` drops below threshold on sensitive domains (health, crisis, emotional, relationships), keyword classifier runs as fallback
- **Classification method logged**: `classification_method` field in risk assessment tracks whether LLM or keyword was the final arbiter

### Distress Corpus & Tests (Phase 17.3)
- **60-entry labeled corpus** (`tests/classification/distress_corpus.yaml`): 36 distress, 24 non-distress across 9 categories (passive ideation, grief, isolation, burnout, etc.)
- **Parametrized test suite** (`tests/classification/test_distress_detection.py`): 72 tests with CI gates - FN rate <= 5%, FP/crisis rate <= 20%
- **20+ new emotional triggers** added to `scenarios/domains/emotional.yaml`: `completely hopeless`, `empty inside`, `nothing matters`, `taking a real toll`, `toll on me`, `consuming me`, `haven't felt anything`, and more

### Sanity Check (Phase 17.4)
- **Logistics + distress guard**: If LLM returns `logistics` but `distress_present=True` OR `emotional_intensity >= 5`, keyword classifier re-runs and can override to the correct domain
- **Override signal logged**: `sanity_check_override` field in risk assessment with trigger reason (`distress_present` or `intensity=X.X`)
- **Policy transparency**: Sanity check overrides logged via `_log_policy()` for UI transparency panel

### Quality
- **Crisis trigger refinements**: Removed `this is the end` (humour false positive); added `better off without me`, `written letters to`, `won't be around`, `before it's too late`, `after i'm gone`
- **Social greeting tone fix**: Casual greetings (`how are you`, `hey hommie`) no longer receive the robotic "I am software. I do not have evenings or feelings." response - now warm and brief
- **Corpus-validated FN rate**: 0% false negatives on 36-example distress corpus (target was <= 5%)

---

## v1.5 (2026-03-10) - UI Polish & Model Upgrade

**"An archangel that doesn't want to be worshipped."**

UI overhaul, human-readable transparency, custom avatars, dual-model architecture, and crisis detection hardening.

### UI
- **Custom chat avatars**: Pulse icon for assistant, person silhouette for user - no more generic bot/human icons
- **Chat CSS fixes**: Removed `white-space: pre-wrap` that broke list formatting and caused wall-of-text on follow-up messages. List numbers now inline with content via `display: inline` on `li p` elements
- **Compact transparency panel**: Rewrote "Why this response?" from 4-row grid layout to single-column plain language. Removed numeric risk scores in favor of human-readable labels (sensitive topic / high sensitivity / standard)
- **Tighter expander spacing**: Reduced paragraph and caption margins inside expanders
- **Passive ideation triggers**: Added 15 crisis triggers for metaphorical distress language ("thinking drowning", "tired of living", etc.) and 8 escalation markers

### Model Architecture
- **Dual-model setup**: Chat responses via `qwen2.5:7b-instruct` (better quality, less hallucination), classification via `mistral:7b-instruct` (fast, proven accuracy)
- **Temperature tuned**: Reduced from 0.95 to 0.7 for more focused, thorough responses
- **Ollama external storage**: Support for models on external drives via `OLLAMA_MODELS` environment variable

### Documentation
- **README**: Updated model recommendations to `qwen2.5:7b-instruct`
- **.env.example**: Updated defaults and classifier model recommendation
- **ROADMAP**: Phase 17.6 (transparency rewrite) marked partially complete

---

## v1.4 (2026-02-28) - Distribution & Safety

**"Easier to start. Safer for everyone."**

Docker one-liner, README rewrite, global crisis resources, coverage baseline, and open community channels.

### Distribution
- **Docker one-liner**: `docker compose up` starts both empathySync and Ollama - model pulls automatically on first run, no manual step needed
- **Auto-pull (non-Docker)**: `install.sh` now pulls the model configured in `.env` automatically if Ollama is running but the model is not yet present - no manual `ollama pull` needed
- **Any Ollama model**: `OLLAMA_MODEL` in `.env` accepts any model - `llama3.2`, `mistral:7b`, `qwen2.5:3b`, whatever you have

### Safety
- **Non-US crisis resources**: crisis.yaml now surfaces 12 regional crisis lines directly in every crisis response - UK, Canada, Australia, Nigeria, South Africa, India, Germany, France, Brazil, Philippines, Kenya

### Documentation
- **README rewrite**: Leads with what makes empathySync unique - the only AI assistant built to make itself less needed
- **Ollama reframed**: Positioned as a capability, not a prerequisite
- **Docker as Option 1**: Lowest-friction path now at the top of Quick Start

### Quality
- **pytest-cov configured**: Coverage reporting enabled, 53.82% baseline established (443 tests)
- **GitHub topics added**: `ollama`, `local-first`, `humane-tech`, `privacy`, `anti-engagement`, `mental-health`, `ai-assistant`, `streamlit`
- **GitHub Discussions enabled**: Community Q&A channel open

### Stats
- 443 tests passing
- 53.82% test coverage
- CI green on Python 3.9, 3.10, 3.11, 3.12

---

## v1.3 (2026-02-11) - Hardening Release

**"The restraint is the feature."**

Phases 16.5–16.10 complete. Type safety, performance optimization, security hardening, god class decomposition, expanded test coverage, and centralized configuration.

### Type Safety (Phase 16.5)
- **Type-safe enums**: `Domain`, `Intent`, `EmotionalWeight`, `ClassificationMethod` -`str, Enum` pattern for backward compatibility
- **Dataclasses**: `RiskAssessment` and `LLMClassification` with dict-compatible access (`__getitem__`, `.get()`, `to_dict()`) and `__post_init__` validation

### Performance (Phase 16.6)
- **httpx migration**: Replaced `requests` with `httpx` -shared connection-pooling client via `get_http_client()`
- **Pre-compiled regex**: Module-level `_RE_JSON_STRICT` and `_RE_JSON_PERMISSIVE` patterns for hot-path classification
- **Injectable http_client**: All Ollama-calling code accepts `http_client` parameter for testability

### Security Hardening (Phase 16.7)
- **Atomic lock file**: `O_CREAT | O_EXCL` flags eliminate TOCTOU race condition in `lockfile.py`
- **SQL injection prevention**: `_VALID_COLUMNS` frozenset whitelist in `storage_backend.py` validates column names before interpolation
- **Input length validation**: `MAX_CLASSIFY_LENGTH = 5000` with graceful truncation in WellnessGuide and LLMClassifier
- **Secrets cleanup**: `.env.example` sanitized with `SECRET_KEY=change-me-to-a-random-string` placeholder

### Architecture (Phase 16.8)
- **OllamaClient extracted**: HTTP layer pulled from WellnessGuide into `src/models/ollama_client.py` -`generate()`, `generate_stream()`, `check_health()`
- **EmotionalWeightAssessor extracted**: Weight logic pulled from RiskClassifier into `src/models/emotional_weight_assessor.py`
- Both parent classes delegate via facade pattern

### Test Coverage (Phase 16.9)
- **+83 new tests** across 4 new test files:
  - `test_write_gate.py` (11 tests): state transitions, `@require_write` decorator
  - `test_trusted_network.py` (57 tests): person management, reach-outs, prompts, handoff, error handling
  - `test_helpers.py` (10 tests): logging, validation, formatting
  - `test_llm_classifier.py` additions (5 tests): error injection -timeout, connection refused, malformed JSON, empty response, HTTP 500

### Configuration (Phase 16.10)
- **Centralized tunables**: `scenarios/config/system_defaults.yaml` with 100+ settings organized by component
- **Config accessor**: `ScenarioLoader.get_default(*keys, fallback=)` for nested config lookup
- **OllamaClient wired**: Timeout, token limits, and temperature loaded from config

### CI Fixes
- Python 3.9 compatibility: `Optional[httpx.Client]` instead of `httpx.Client | None` (PEP 604)
- Black 25.9.0 pinning for consistent formatting across local and CI
- Flake8 F811 fix: renamed shadowed `settings` variable

### Stats
- **443 tests passing** (up from 360)
- CI green on Python 3.9, 3.10, 3.11, 3.12
- `requests` dependency removed, replaced with `httpx>=0.26.0`

### Breaking Changes
- `requests` replaced by `httpx` -run `pip install -r requirements.txt` after upgrading

---

## v1.0 (2026-02-06) -Core Decoupling & Streaming

**"The soul as a library."**

Phase 16 complete. The conversation engine is now framework-agnostic and can be embedded in any Python project. Streaming support for real-time response delivery.

### Core Decoupling (Phase 16)
- **ConversationSession class**: Framework-agnostic session manager that owns all conversation state. Single entry point: `process_message()` → `ConversationResult`.
- **InterfaceAdapter protocol**: Minimal contract for UI adapters. Any interface can drive the conversation engine.
- **CLIAdapter**: Direct terminal interface (`empathysync --mode cli`) proving the abstraction works.
- **Streamlit refactored**: `app.py` now uses `ConversationSession` instead of scattered `st.session_state`.

### Streaming Support
- **Real-time token streaming**: Responses stream as they're generated instead of blocking for completion.
- **`generate_response_stream()`**: Generator method in `WellnessGuide` that yields tokens progressively.
- **`process_message_stream()`**: Session-level streaming API with `finalize_stream()` for post-stream metadata.
- **CLI streaming**: Tokens appear in terminal as generated (`sys.stdout.write` + flush).
- **Streamlit streaming**: Uses `st.write_stream()` for progressive display.
- **Safety preserved**: Pre-LLM pipeline runs synchronously. Crisis/harmful returns complete immediately.

### Fixes
- **LLM classifier false positive**: Geopolitical questions ("Do you think war is upon us?") no longer classified as crisis.
- **Black formatting**: Pre-commit hook added to catch formatting issues before CI.

### Stats
- **360 tests passing** (up from 323)
- **15 new streaming tests**
- All existing functionality preserved

---

## v0.9-beta (2026-02-01) -First Public Release

**"Help that knows when to stop."**

This is the first tagged release of empathySync -a local-first AI assistant that provides full help for practical tasks while applying restraint on sensitive topics. 14 phases of development, 323 tests passing.

### Core Engine
- **Dual-mode operation**: Full assistance for practical tasks (emails, code, explanations). Brief, restrained responses for sensitive topics (relationships, health, finances, spirituality) with human redirect.
- **LLM-based classification** (Phase 9): Context-aware domain detection via Ollama replaces brittle keyword matching. Hybrid system: fast-path for safety-critical, LLM for nuance, keyword fallback.
- **Practical technique detection** (Phase 9.1): "How do I meditate?" gets full help. "Is this God's will?" gets restraint + human redirect. Works across all sensitive domains.
- **7-step safety pipeline**: Cooldown check → risk assessment → hard stop → turn limits → dependency intervention → identity reminder → response generation.
- **Crisis intervention**: Immediate redirect to professional resources. Never engages with crisis content. Never apologizes for safety interventions. Post-crisis deflection handling ("just joking") stays firm.

### Anti-Dependency Systems
- **Dependency scoring** (12-message lookback): Tracks frequency and repetition patterns. Graduated interventions at 5 levels.
- **Anti-engagement metrics** (Phase 7): Tracks sensitive topic usage only -practical tasks are neutral. Week-over-week comparison where fewer sensitive sessions = success.
- **"What Would You Tell a Friend?"** (Phase 8): Flips the question on sensitive topics to help users access their own wisdom.
- **"Before You Send" pause** (Phase 8): Suggests sleeping on high-stakes messages (resignations, difficult conversations).
- **"Have You Talked to Someone?" gate** (Phase 8): Asks if you've talked to a human before continuing on heavy topics.
- **Competence graduation** (Phase 3): Notices when you're using the same task type repeatedly and gently suggests building that skill yourself.
- **Cooldown enforcement**: Blocks sessions after 7+ sessions/day, 120+ minutes/day, or dependency score >= 8.

### Human Connection
- **Trusted network management** (Phase 5): Add your real humans. Domain-specific suggestions for who to talk to.
- **Context-aware handoff templates**: Pre-written messages for reaching out -"need to talk", "reconnecting", "hard conversation", "asking for help". Auto-suggested based on session content.
- **Connection building** (Phase 12): For users with empty networks -signpost categories (community groups, volunteering, support groups, classes) and first-contact templates for initiating new connections.
- **Handoff tracking**: "Did you reach out?" → "How did it go?" with success metrics.

### Transparency & Tracking
- **Decision transparency panel** (Phase 6): "Why this response?" shows domain detected, mode, word limit, policy actions.
- **Session summaries** with JSON export.
- **"My Patterns" dashboard** (Phase 7): Sensitive topics ↓ = good. Human reach-outs ↑ = good. Practical tasks = neutral.
- **Policy event logging**: Every safety decision is recorded with reasons.

### Context & Intelligence
- **Context persistence** (Phase 6.5): System maintains emotional context across turns. "Caught my boyfriend cheating" → "let's brainstorm" still gets appropriate handling.
- **Topic threading**: Detects continuation messages via pronouns, affirmatives, topic hints.
- **Context decay**: High-weight context persists 5-7 turns, then fades naturally.
- **Emotional weight awareness** (Phase 2): Recognizes heavy practical tasks (resignation emails, apologies, condolences) and adds brief human acknowledgment.
- **Session intent check-in** (Phase 4): "What brings you here?" with connection-seeking detection.

### Data & Persistence
- **Local-first**: All data stored on your machine. No external API calls, no telemetry.
- **Atomic JSON writes** (Phase 11): Write to temp file → fsync → atomic rename. No data corruption on crash.
- **Optional SQLite backend**: WAL mode, full transactions, schema migrations. Enable with `USE_SQLITE=true`.
- **Multi-device sync safety** (Phase 11): Heartbeat-based lock file prevents data conflicts. Write gate blocks all mutations when another device has the lock.
- **Schema versioning**: Automatic migration on load.

### Distribution
- **One-command setup**: `bash install.sh` -checks Python, creates venv, installs deps, configures .env, verifies Ollama.
- **pip install**: `pip install -e ".[dev]"` with `empathysync` CLI entry point.
- **Docker Compose**: `docker compose up` starts both empathySync and Ollama together.
- **Startup health checks** (Phase 13): Validates Ollama connectivity, model availability, data directory, SQLite -with actionable error messages.

### Known Limitations
- Requires Ollama running locally (no cloud LLM support by design).
- Classification quality depends on the local model -larger models give better results.
- Single-user design. No multi-user or authentication system.

### Requirements
- Python 3.9+
- [Ollama](https://ollama.com/) with a downloaded model
- 8GB RAM recommended (4GB minimum)

---

*"We optimize exits, not engagement."*
