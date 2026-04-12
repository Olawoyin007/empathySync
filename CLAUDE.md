# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

empathySync is a local-first AI assistant that provides **full help for practical tasks** while applying **restraint on sensitive topics**. It runs entirely on local hardware via Ollama integration - no external API calls.

**Core Philosophy**: "Help that knows when to stop"
- **Practical tasks** (writing emails, coding, explaining concepts): Full assistant capability, no word limits
- **Sensitive topics** (emotional, financial decisions, health, relationships): Brief responses, redirects to humans

The system actively works to reduce user dependency on AI for emotional support while being genuinely helpful for everyday practical tasks.

## Development Commands

```bash
# Quick setup (one command)
bash install.sh

# Or manual setup
pip install -e ".[dev]"     # Editable install with dev tools
pip install -r requirements.txt  # Alternative: just core deps

# Run the application
streamlit run src/app.py    # Direct
empathysync                 # Via CLI entry point (after pip install -e .)

# Docker (app + Ollama together)
docker compose up           # Starts both services

# Run tests (443 tests covering all core components)
pytest tests/

# Run tests with coverage
pytest tests/ --cov=src

# Linting and formatting
black src/
flake8 src/
mypy src/

# Validate YAML scenarios
python -c "import yaml; yaml.safe_load(open('scenarios/domains/money.yaml'))"
```

## Required Environment Variables

Configure in `.env` file (see `.env.example`):

**Required:**
- `OLLAMA_HOST` - Ollama server URL (e.g., `http://localhost:11434`)
- `OLLAMA_MODEL` - Model name to use (e.g., `llama2`)
- `OLLAMA_TEMPERATURE` - Temperature for responses (default: 0.7)

**Optional:**
- `ENVIRONMENT` - development/production
- `DEBUG` - true/false
- `LOG_LEVEL` - DEBUG/INFO/WARNING/ERROR
- `STORE_CONVERSATIONS` - true/false
- `CONVERSATION_RETENTION_DAYS` - integer (default: 30)
- `LLM_CLASSIFICATION_ENABLED` - true/false (default: true) - enables LLM-based intelligent classification (Phase 9)
- `OLLAMA_CLASSIFIER_MODEL` - optional dedicated model for classification (e.g., `qwen2.5:3b-instruct`). Falls back to `OLLAMA_MODEL` if not set. Smaller models run classification faster (~9s vs ~19s)

**Storage Backend (Phase 11):**
- `USE_SQLITE` - true/false (default: false) - enables SQLite backend with WAL mode
- `ENABLE_DEVICE_LOCK` - true/false (default: false) - enables heartbeat-based lock file for multi-device sync
- `LOCK_STALE_TIMEOUT` - integer (default: 300) - seconds until a lock is considered stale

**Optional PostgreSQL** (all or none): `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

## Architecture

### Directory Structure

```
empathySync/
├── src/                          # Application source code
│   ├── app.py                   # Streamlit entry point
│   ├── cli.py                   # CLI entry point: `empathysync` or `empathysync --mode cli` (Phase 14, 16)
│   ├── config/settings.py       # Environment configuration
│   ├── models/
│   │   ├── ai_wellness_guide.py # Core conversation engine -delegates to OllamaClient
│   │   ├── ollama_client.py     # HTTP layer for Ollama API (extracted Phase 16.8)
│   │   ├── emotional_weight_assessor.py # Emotional weight logic (extracted Phase 16.8)
│   │   ├── risk_classifier.py   # Risk assessment + intent detection -delegates to EmotionalWeightAssessor
│   │   ├── llm_classifier.py    # LLM-based classification with pre-compiled regex (Phase 9, 16.6)
│   │   ├── enums.py             # Domain, Intent, EmotionalWeight, ClassificationMethod enums (Phase 16.5)
│   │   ├── data_contracts.py    # RiskAssessment, LLMClassification dataclasses (Phase 16.5)
│   │   ├── conversation_session.py # Framework-agnostic session manager (Phase 16)
│   │   └── conversation_result.py  # Structured result dataclass (Phase 16)
│   ├── interfaces/              # Interface adapters (Phase 16)
│   │   ├── adapter.py           # InterfaceAdapter protocol
│   │   └── cli_adapter.py       # Terminal interface adapter
│   ├── prompts/
│   │   └── wellness_prompts.py  # Dynamic prompt generation (~350 lines)
│   └── utils/
│       ├── helpers.py           # Logging and utilities
│       ├── health_check.py      # Startup health checks -uses httpx (Phase 13, 16.6)
│       ├── http_client.py       # Shared httpx.Client with connection pooling (Phase 16.6)
│       ├── wellness_tracker.py  # Session/check-in/metrics tracking (~1400 lines)
│       ├── trusted_network.py   # Human network management (~500 lines)
│       ├── scenario_loader.py   # YAML knowledge base loader + get_default() for tunables (~1300 lines)
│       ├── storage_backend.py   # Unified storage with _VALID_COLUMNS SQL injection prevention (Phase 11, 16.7)
│       ├── lockfile.py          # Atomic lock file with O_CREAT|O_EXCL (Phase 11, 16.7)
│       └── write_gate.py        # Centralized write permission control (Phase 11)
├── scenarios/                    # Knowledge base (34+ YAML files)
│   ├── config/                  # System defaults and tunables (Phase 16.10)
│   │   └── system_defaults.yaml # 100+ centralized tunables
│   ├── domains/                 # 8 risk domains (crisis, harmful, health, money, emotional, relationships, spirituality, logistics)
│   ├── emotional_markers/       # 4 intensity levels
│   ├── emotional_weight/        # Task weight detection (high/medium/low)
│   ├── classification/          # LLM classifier prompts and config
│   ├── connection_building/     # Signposts and first-contact templates (Phase 12)
│   ├── graduation/              # Competence graduation prompts
│   ├── handoff/                 # Human handoff templates
│   ├── intents/                 # Session intent configuration
│   ├── interventions/           # Dependency, boundaries
│   ├── metrics/                 # Success metrics configuration
│   ├── prompts/                 # Check-ins, mindfulness, styles
│   ├── responses/               # Fallbacks, safe alternatives, base prompt
│   ├── transparency/            # Explanation templates
│   └── wisdom/                  # Immunity building prompts
├── tests/                       # Pytest test suite (443 tests)
├── data/                        # Local user data (JSON files)
├── docs/                        # Documentation
├── logs/                        # Application logs
├── pyproject.toml               # Package metadata, dependencies, entry points (Phase 14)
├── install.sh                   # One-command setup script for Linux/Mac (Phase 14)
├── Dockerfile                   # Container image for empathySync (Phase 14)
└── docker-compose.yml           # App + Ollama orchestration (Phase 14)
```

### Core Components

**Entry Point**: [src/app.py](src/app.py) - Streamlit application with:
- Chat interface (communication style auto-adjusts based on detected domain)
- Wellness sidebar with usage health indicators
- Reality check panel showing dependency signals
- Trusted network setup and human handoff templates
- Session tracking, export, and policy action transparency

**Models**:
- [src/models/ai_wellness_guide.py](src/models/ai_wellness_guide.py) - `WellnessGuide` class: main conversation engine with 7-step safety pipeline, delegates HTTP calls to `OllamaClient`, streaming via `generate_response_stream()`
- [src/models/ollama_client.py](src/models/ollama_client.py) - `OllamaClient` class: extracted HTTP layer for Ollama API -`generate()`, `generate_stream()`, `check_health()`. Loads tunables from `system_defaults.yaml` (Phase 16.8)
- [src/models/emotional_weight_assessor.py](src/models/emotional_weight_assessor.py) - `EmotionalWeightAssessor` class: extracted from RiskClassifier -`measure_intensity()`, `assess_weight()`, `needs_reflection_redirect()`, `get_response_modifier()` (Phase 16.8)
- [src/models/risk_classifier.py](src/models/risk_classifier.py) - `RiskClassifier` class: detects conversation domain (8 domains), delegates emotional weight to `EmotionalWeightAssessor`, intent detection
- [src/models/llm_classifier.py](src/models/llm_classifier.py) - `LLMClassifier` class: LLM-based classification with caching, pre-compiled regex patterns, injectable `http_client`, input truncation at 5000 chars (Phase 9, 16.6, 16.7)
- [src/models/enums.py](src/models/enums.py) - Type-safe enums: `Domain`, `Intent`, `EmotionalWeight`, `ClassificationMethod` -`str, Enum` pattern for backward compatibility (Phase 16.5)
- [src/models/data_contracts.py](src/models/data_contracts.py) - `RiskAssessment` and `LLMClassification` dataclasses with dict-compatible access (`__getitem__`, `.get()`, `to_dict()`) and `__post_init__` validation (Phase 16.5)
- [src/models/conversation_session.py](src/models/conversation_session.py) - `ConversationSession` class: framework-agnostic session manager. Entry points: `process_message()` → `ConversationResult` or `process_message_stream()` + `finalize_stream()`
- [src/models/conversation_result.py](src/models/conversation_result.py) - `ConversationResult` dataclass: structured return type containing response, risk assessment, policy actions, and UI hints

**Interfaces** (Phase 16):
- [src/interfaces/adapter.py](src/interfaces/adapter.py) - `InterfaceAdapter` protocol: minimal contract for UI adapters (render result, prompt interactions)
- [src/interfaces/cli_adapter.py](src/interfaces/cli_adapter.py) - `CLIAdapter` class: terminal interface for `empathysync --mode cli`

**Prompts**:
- [src/prompts/wellness_prompts.py](src/prompts/wellness_prompts.py) - `WellnessPrompts` class: builds system prompts via 3-layer composition (base rules + style modifier + risk context)

**Utils**:
- [src/utils/http_client.py](src/utils/http_client.py) - Shared `httpx.Client` with connection pooling. All Ollama-calling code uses `get_http_client()` (Phase 16.6)
- [src/utils/wellness_tracker.py](src/utils/wellness_tracker.py) - `WellnessTracker` class: tracks sessions, check-ins, policy events; calculates dependency signals; enforces cooldowns
- [src/utils/trusted_network.py](src/utils/trusted_network.py) - `TrustedNetwork` class: manages trusted contacts, domain-specific suggestions, reach-out history, connection health metrics, signposts for finding connection, first-contact templates (Phase 12)
- [src/utils/scenario_loader.py](src/utils/scenario_loader.py) - `ScenarioLoader` class: singleton loader for YAML knowledge base with caching, hot-reload, `get_system_defaults()` and `get_default(*keys, fallback=)` for centralized config (Phase 16.10)
- [src/utils/helpers.py](src/utils/helpers.py) - Logging setup and environment validation
- [src/utils/database.py](src/utils/database.py) - SQLite database layer with WAL mode, transactions, schema migrations (Phase 11)
- [src/utils/storage_backend.py](src/utils/storage_backend.py) - Unified storage with `_VALID_COLUMNS` whitelist for SQL injection prevention (Phase 11, 16.7)
- [src/utils/lockfile.py](src/utils/lockfile.py) - Atomic lock file using `O_CREAT | O_EXCL` flags for race-free acquisition (Phase 11, 16.7)
- [src/utils/write_gate.py](src/utils/write_gate.py) - Centralized write permission control for read-only mode (Phase 11)
- [src/utils/health_check.py](src/utils/health_check.py) - Startup health checks using httpx: Ollama server/model availability, data directory, SQLite database (Phase 13, 16.6)

**Config**:
- [src/config/settings.py](src/config/settings.py) - `Settings` class: environment-based configuration with validation

### Two Operating Modes

**1. Practical Mode** (logistics domain OR practical technique questions)
- Triggered by:
  - `logistics` domain: writing requests, coding, explanations, general questions
  - `is_practical_technique: true` in any domain (Phase 9.1): "How do I meditate?", "What are budgeting methods?"
- Behavior: Full assistant capability
  - No word limits (up to 2000 tokens)
  - Markdown formatting, code blocks, lists allowed
  - Complete the task thoroughly
  - No identity reminders or therapeutic framing

**2. Reflective Mode** (sensitive domains with guidance questions)
- Triggered by: emotional content, financial decisions, health concerns, relationships, spirituality
  - Only when `is_practical_technique: false` (asking for guidance, not techniques)
  - Examples: "Should I get this surgery?", "Is this God's will?", "Should I break up?"
- Behavior: Brief, restrained responses
  - Word limits enforced (50-150 words)
  - Plain prose, no formatting
  - Redirects to human support
  - Identity reminders every 6 turns

**Phase 9.1: Practical Technique Detection**
The LLM classifier distinguishes between:
- **Technique questions** (`is_practical_technique: true`): "How do I X?" → Full practical help
- **Guidance questions** (`is_practical_technique: false`): "Should I X?" → Restraint + human redirect

| Domain | Technique Question | Guidance Question |
|--------|-------------------|-------------------|
| Health | "How do I do a proper squat?" ✓ | "Should I get this surgery?" ✗ |
| Money | "How do I create a budget?" ✓ | "Should I invest in crypto?" ✗ |
| Relationships | "How do I write a wedding toast?" ✓ | "Should I break up?" ✗ |
| Spirituality | "How do I meditate?" ✓ | "Is this my calling?" ✗ |

### Data Flow (Safety Pipeline)

0. **Startup Health Checks** (Phase 13): Ollama server reachable, model available, data directory writable, SQLite accessible. Critical failures block the app with actionable fix instructions.
1. User input received in Streamlit chat
2. **Post-Crisis Check**: If previous turn was a crisis intervention, handle deflection patterns ("just joking") with firm, non-apologetic response. Never apologize for crisis interventions.
3. **Cooldown Check**: `WellnessTracker.should_enforce_cooldown()` blocks if usage limits exceeded
4. **Risk Assessment**: `RiskClassifier.classify()` returns domain, emotional intensity, dependency risk, `is_practical_technique`, and combined risk weight
5. **Mode Selection**: `logistics` domain OR `is_practical_technique=true` → Practical Mode, otherwise → Reflective Mode
6. **Hard Stop Check**: Crisis/harmful domains trigger immediate intervention
7. **Turn Limit Check**: Domain-specific turn limits enforced (configurable in `system_defaults.yaml`):
   - `logistics`: 30 turns (practical tasks)
   - `money`: 15 turns
   - `health`: 15 turns
   - `relationships`: 15 turns
   - `spirituality`: 10 turns
   - `crisis/harmful`: 1 turn
8. **Dependency Intervention**: Graduated responses if dependency score exceeds thresholds
9. **Identity Reminder**: Injected every 6 turns (only in Reflective Mode)
10. System prompt composed (base + style + mode-specific rules + post-crisis context if applicable), Ollama called locally
11. **Response streams** in real-time via `generate_response_stream()` (tokens yielded as generated)
12. Response safety-checked via `_contains_harmful_content()` before/during display

### Risk Assessment

The `RiskClassifier` produces:
```python
{
    "domain": str,                  # money, health, relationships, spirituality, crisis, harmful, emotional, logistics
    "emotional_weight": str,        # high_weight, medium_weight, low_weight (for practical tasks)
    "emotional_weight_score": float,  # 0-10 scale
    "emotional_intensity": float,   # 0-10 scale
    "dependency_risk": float,       # 0-10 scale (from conversation patterns)
    "risk_weight": float,           # Combined 0-10 risk score
    "classification_method": str,   # "llm" or "keyword" (Phase 9)
    "is_personal_distress": bool,   # LLM-detected personal vs general topic (Phase 9)
    "is_practical_technique": bool, # True = "how to" question, False = guidance question (Phase 9.1)
    "llm_confidence": float,        # 0-1 confidence score (when LLM used)
    "intervention": dict            # Present if dependency threshold met
}
```

**Mode Selection Logic** (Phase 9.1):
```python
is_practical = domain == "logistics" or risk_assessment.get("is_practical_technique", False)
```

### Emotional Weight (Practical Tasks Only)

Separate from emotional intensity, emotional weight measures how "heavy" a practical task is:
- **Emotional intensity**: How emotionally charged is the USER right now?
- **Emotional weight**: How emotionally heavy is the TASK itself?

| Weight Level | Score | Examples | Acknowledgment |
|--------------|-------|----------|----------------|
| high_weight | 8.0 | Resignation, breakup, apology, condolence | Warm acknowledgment appended |
| medium_weight | 5.0 | Negotiation, complaint, asking for help | Brief acknowledgment (optional) |
| low_weight | 2.0 | Grocery list, code help, general questions | None |

For high-weight practical tasks, a brief human acknowledgment is appended:
> "Here's your resignation email.\n\n---\n\nThese transitions are hard. You'll find your words when the time comes."

**Dependency Scoring** (12-message lookback):
- Base factor: frequency × 0.7 (capped at 6.0)
- Repetition boost: unique prefix ratio × 4.0 max
- Final score capped at 10.0

### Scenarios Knowledge Base

All domain rules, prompts, and interventions are defined in YAML files under `scenarios/`. See [scenarios/README.md](scenarios/README.md) for editing guidelines.

**Domain Files** (`scenarios/domains/`):
| Domain | Risk Weight | Description |
|--------|-------------|-------------|
| crisis | 10.0 | Suicidal ideation, self-harm |
| harmful | 10.0 | Illegal/violent intent |
| health | 7.0 | Medical concerns (symptoms, medications) |
| money | 6.0 | Financial topics (loans, debt, investments) |
| emotional | 5.0 | General emotional expressions |
| relationships | 5.0 | Interpersonal dynamics (partner, family) |
| spirituality | 4.0 | Religious/spiritual matters |
| logistics | 1.0 | Neutral/default topics |

**Hot Reloading** (for development):
```python
from src.utils.scenario_loader import get_scenario_loader
loader = get_scenario_loader()
loader.reload()  # Picks up changes from disk
```

### Data Persistence

All user data is stored locally with **atomic writes**, **schema versioning**, and optional **SQLite backend**.

For detailed multi-device sync documentation, see [docs/persistence.md](docs/persistence.md).

**Storage Backends:**
- **JSON Backend** (default): Simple, human-readable files with atomic writes
- **SQLite Backend** (`USE_SQLITE=true`): WAL mode, transactions, better concurrency

**Write Safety (JSON):**
- Writes to temp file (`.wellness_data_*.tmp`)
- Flushes and fsyncs to disk
- Atomic rename via `os.replace()` (POSIX-guaranteed atomic)
- Corrupted files backed up as `.corrupted.{timestamp}.json`

**Write Safety (SQLite):**
- WAL mode (`PRAGMA journal_mode=WAL`) for crash safety
- `PRAGMA synchronous=FULL` for durability
- `PRAGMA foreign_keys=ON` enforced per-connection
- Checkpoint on close (`wal_checkpoint(TRUNCATE)`)
- Schema v2: `ON DELETE CASCADE` for reach_outs → trusted_people

**Write Gate (Phase 11):**
When another device holds the lock (`ENABLE_DEVICE_LOCK=true`), all write operations are blocked:
- `src/utils/write_gate.py` provides centralized control
- All storage backend write methods check permission before executing
- Checkpoint is skipped in read-only mode
- UI shows "Writes blocked" indicator in sidebar

**`data/wellness_data.json`** (or SQLite `empathySync.db`):
```json
{
  "schema_version": 1,    // For safe migrations
  "check_ins": [...],       // Daily wellness scores (1-5 scale)
  "usage_sessions": [...],  // Session metadata (duration, turns, domains, risk)
  "policy_events": [...],   // Transparency log of policy actions
  "created_at": "datetime"
}
```

**`data/trusted_network.json`** (or SQLite tables):
```json
{
  "schema_version": 1,    // For safe migrations
  "people": [...],      // Trusted contacts with domains and relationship info
  "reach_outs": [...],  // History of human connection attempts (cascade delete on person removal)
  "created_at": "datetime"
}
```

**Schema Versions:**
- v1: Initial schema with all required fields
- v2 (SQLite): Added `ON DELETE CASCADE` to reach_outs foreign key

**Schema Migration:** On load, files/databases are automatically migrated from older schema versions. Migration functions run sequentially (v0→v1→v2...) and save the updated data.

### Cooldown Enforcement

`WellnessTracker.should_enforce_cooldown()` returns true when:
- 7+ sessions today
- 120+ minutes today
- Dependency score >= 8

### Key Design Constraints (from MANIFESTO.md)

- All processing must remain local - no external API calls
- No telemetry, engagement metrics, or behavior tracking
- User data belongs to the user - stored only in local JSON files
- Features must center human wellbeing and psychological safety
- Reject any feature that enables manipulation or exploits user vulnerability
- Never optimize for engagement or increased usage

### UI Components (app.py)

- **Chat Interface**: Main conversation area with message history
- **Wellness Sidebar**: Health indicators, check-in prompts, toggle panels
- **Reality Check Panel**: Dependency signals with human-readable warnings
- **Trusted Network Setup**: Add/manage trusted contacts by domain
- **Bring Someone In**: Pre-written templates for human handoff (need_to_talk, reconnecting, checking_in, hard_conversation, asking_for_help)
- **Session Export**: Download conversation as JSON
- **Policy Transparency**: Displays last policy action with explanation

### Testing

443 tests across multiple test files:
- [tests/test_wellness_guide.py](tests/test_wellness_guide.py) - Core tests: ScenarioLoader, RiskClassifier, WellnessPrompts, WellnessGuide, HealthChecks, Streaming
- [tests/test_llm_classifier.py](tests/test_llm_classifier.py) - LLM classification, httpx mocks, error injection (timeout, connection refused, malformed JSON)
- [tests/test_persistence.py](tests/test_persistence.py) - Database, StorageBackend, LockFile modules
- [tests/test_write_gate.py](tests/test_write_gate.py) - Write gate state transitions, `@require_write` decorator (11 tests, Phase 16.9)
- [tests/test_trusted_network.py](tests/test_trusted_network.py) - Person management, reach-outs, prompts, connection building, handoff, error handling (57 tests, Phase 16.9)
- [tests/test_helpers.py](tests/test_helpers.py) - Logging setup, environment validation, formatting utilities (10 tests, Phase 16.9)

### Key Patterns

- **Singleton Pattern**: `ScenarioLoader` via `get_scenario_loader()`, `StorageBackend` via `get_storage_backend()`
- **Facade Pattern**: `WellnessGuide` → `OllamaClient`, `RiskClassifier` → `EmotionalWeightAssessor` (Phase 16.8)
- **Shared HTTP Client**: Module-level `httpx.Client` with connection pooling via `get_http_client()` (Phase 16.6)
- **3-Layer Prompt Composition**: Base rules + style modifier + risk context
- **Graduated Interventions**: 5 dependency levels (none, early_pattern, mild, concerning, high)
- **Session State Tracking**: Turns, domains, max risk, last policy action, post-crisis turn
- **Post-Crisis Protection**: Tracks when crisis intervention occurred, prevents LLM from apologizing for safety actions
- **Hot Reload Support**: `loader.reload()` and `loader.clear_cache()`
- **Centralized Tunables**: `scenarios/config/system_defaults.yaml` with `get_default(*keys, fallback=)` (Phase 16.10)
- **Transparency Logging**: All policy decisions logged with reasons
- **Defense-in-Depth Write Protection**: UI disabling → write gate flag → storage method checks (Phase 11)
- **Atomic Lock File**: `O_CREAT | O_EXCL` for race-free lock acquisition (Phase 16.7)
- **SQL Injection Prevention**: `_VALID_COLUMNS` whitelist validates column names before interpolation (Phase 16.7)
- **Type-Safe Enums**: `str, Enum` pattern for backward-compatible domain/intent constants (Phase 16.5)
- **Storage Backend Abstraction**: Unified interface for JSON/SQLite with automatic migration (Phase 11)
- **Streaming Response**: `generate_response_stream()` yields tokens progressively for real-time display (Phase 16)

## Documentation Maintenance

**Rule: docs must be updated before merging any PR that changes behavior, structure, or features. Never leave docs stale.**

| Document | Update when |
|----------|-------------|
| `README.md` | New features shipped, installation changes, model recommendations change, new platform/browser support |
| `ROADMAP.md` | Phase completed - mark ✅; new phase planned - add entry |
| `CHANGELOG.md` | Any significant code change - add entry before merge (version bump not required for sub-phases) |
| `docs/architecture.md` | Safety pipeline steps change, new components added, component relationships change, new key patterns |
| `CLAUDE.md` (this file) | Directory structure changes, new env vars, new key patterns, new design constraints |

### Per-change checklist

**New feature or phase complete:**
- [ ] ROADMAP.md: mark phase ✅
- [ ] CHANGELOG.md: add entry describing what changed and why
- [ ] docs/architecture.md: update relevant section (pipeline diagram, component diagram, etc.)
- [ ] README.md: update if user-facing (new commands, new settings, new supported platforms)

**Safety pipeline change (new step, changed step order, new signal):**
- [ ] docs/architecture.md: update the pipeline diagram and step numbering
- [ ] CHANGELOG.md: document the change
- [ ] CLAUDE.md: update Data Flow section if step numbering changes

**New component, class extracted, or utility added:**
- [ ] CLAUDE.md: add to Models / Utils / Interfaces sections with file path and responsibilities
- [ ] docs/architecture.md: add to Component Relationships diagram

**New environment variable:**
- [ ] CLAUDE.md: add to Required Environment Variables
- [ ] `.env.example`: add with comment
- [ ] README.md: if user-facing

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the phased implementation plan covering:
- Phases 1-9.1: Core engine, safety pipeline, dual-mode, LLM classification ✅
- Phase 11: Persistence Hardening & Multi-Device Sync ✅
- Phase 12: Connection Building ✅
- Phase 13-15: Health checks, distribution, CI ✅
- Phase 16: Core Decoupling & Interface Abstraction ✅
- Phase 16.5: Type-safe enums and dataclasses ✅ (Partial)
- Phase 16.6: httpx migration and pre-compiled regex ✅ (Partial)
- Phase 16.7: Security hardening -atomic locks, SQL injection prevention ✅ (Partial)
- Phase 16.8: God class decomposition -OllamaClient, EmotionalWeightAssessor ✅ (Partial)
- Phase 16.9: Test coverage expansion -83 new tests ✅ (Partial)
- Phase 16.10: Centralized configuration -system_defaults.yaml ✅ (Partial)
- Phase 16.11: Conversation testing & voice tuning 🔧 NEXT
- Phase 17: Persistent agent daemon 🔜 PLANNED
