# Changelog

All notable changes to empathySync are documented here.

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
