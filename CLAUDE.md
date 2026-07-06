# CLAUDE.md

> **Before any PR**: read `MERGE_CHECKLIST.md`
> **Before any release**: run `python scripts/check_version.py`

## Project Overview

empathySync is a local-first AI assistant that provides full help for practical
tasks while applying deliberate restraint on sensitive topics. It runs entirely
on local hardware via Ollama — no external API calls, no telemetry, no
engagement optimization. The design principle is restraint as architecture:
ethical constraints are enforced in the processing pipeline, not in prompts or
policies that can be bypassed.

## Development Commands

```bash
# Setup
bash install.sh                          # One-command setup (Linux/Mac)
pip install -e ".[dev]"                  # Manual: editable install with dev tools

# Run
streamlit run src/app.py                 # Streamlit web UI (direct)
empathysync                              # CLI entry point → web UI
empathysync --mode cli                   # Terminal mode (no browser)
empathysync --version                    # Print version and exit
empathysync --list-domains               # List supported classification domains
empathysync --list-domains --json        # Same, machine-readable JSON
empathysync --maintenance                # Prune old data, check integrity, exit
empathysync --log-level DEBUG            # Override log verbosity

# Docker (app + Ollama together)
docker compose up

# Tests
pytest tests/                            # Full suite (1053 unit + 20 conversation)
pytest tests/ --cov=src                  # With coverage
pytest tests/ -m "not conversation"      # Skip Ollama-dependent tests
python tests/classification/run_domain_eval.py          # Domain accuracy eval
python tests/classification/run_domain_eval.py --no-llm # Keyword-only baseline

# Quality
black src/
flake8 src/
mypy src/
python scripts/check_version.py          # Verify version strings consistent
```

## Required Environment Variables

See `.env.example` for full documentation and defaults.

**Required:**
- `OLLAMA_HOST` — Ollama server URL (e.g. `http://localhost:11434`)
- `OLLAMA_MODEL` — Engine model (e.g. `gemma3:12b`)
- `OLLAMA_TEMPERATURE` — Response temperature (default: `0.7`)

**Classification:**
- `LLM_CLASSIFICATION_ENABLED` — Enable LLM classifier (default: `true`)
- `OLLAMA_CLASSIFIER_MODEL` — Dedicated classifier model; falls back to
  `OLLAMA_MODEL` if unset. Smaller models run faster (~9s vs ~19s).
- `OLLAMA_SAFETY_MODEL` — Optional additive LlamaGuard model (e.g.
  `llama-guard3:1b`). Off by default. Landed but not yet wired into the pipeline
  (Phase 21.2).

**Storage:**
- `USE_SQLITE` — SQLite backend instead of JSON (default: `false`)
- `ENABLE_DEVICE_LOCK` — Heartbeat lock for multi-device sync (default: `false`)
- `LOCK_STALE_TIMEOUT` — Seconds until a stale lock expires (default: `300`)

**Docker only:**
- `APP_BIND` — Host address to bind to (default: `127.0.0.1`; set `0.0.0.0` for LAN access)
- `APP_PORT` — Host port mapping (default: `8501`)
- `PUID` — Host user ID the container drops to (default: `1000`)
- `PGID` — Host group ID the container drops to (default: `1000`)

## Key Design Constraints

These are non-negotiable. Every feature decision should be checked against them.

- All processing must remain local — no external API calls, ever
- No telemetry, engagement metrics, or behaviour tracking
- User data belongs to the user — stored only in local files
- Restraint is a feature, not a limitation — optimize for exit, not engagement
- Ethical constraints live in the pipeline, not in prompts or guidelines
- Reject any feature that enables manipulation or exploits user vulnerability
- Transparency is mandatory — every policy action is logged and explained

## Testing

```
tests/
├── test_wellness_guide.py          # Core pipeline: classifier, prompts, guide
├── test_llm_classifier.py          # LLM classification, httpx mocks, errors
├── test_conversation_quality.py    # Structural + LLM response quality
│                                     (structural tier: no Ollama required)
│                                     (conversation tier: -m conversation)
├── test_persistence.py             # Database, StorageBackend, LockFile
├── test_write_gate.py              # Write gate state transitions
├── test_trusted_network.py         # Person management, reach-outs, templates
├── test_helpers.py                 # Logging, environment validation
├── test_data_contracts.py          # RiskAssessment, LLMClassification
├── test_conversation_session.py    # ConversationSession orchestration
├── test_validate_scenarios.py      # YAML schema validation
├── test_restraint_memory.py        # Negative invariant: persisted fields ⊆ allowlist
└── classification/
    ├── domain_corpus.yaml          # 94 labeled examples for accuracy eval
    └── run_domain_eval.py          # Per-domain accuracy report
```

Current counts: ~1053 unit tests, 20 conversation quality scenarios.

Pre-existing known failure: `stress_test_001` conversation tier is
non-deterministic (LLM output varies); the structural tier always passes.

## Architecture Reference

Full details are in the docs — do not duplicate them here.

| Topic | Reference |
|-------|-----------|
| Safety pipeline, component relationships, operating modes | `docs/architecture.md` |
| Persistence, storage backends, multi-device sync | `docs/persistence.md` |
| Model benchmarks and recommendations | `docs/model-benchmark.md` |
| Scenario editing guide | `scenarios/README.md` |
| Roadmap (planned phases) | `ROADMAP.md` |
| Completed phase history | `docs/roadmap-history.md` |
| Pre-merge checklist | `MERGE_CHECKLIST.md` |

**Before modifying anything in `src/models/`, `src/utils/`, or the safety
pipeline: read `docs/architecture.md` first.** It is the authoritative
reference for component relationships and pipeline step ordering. Changes
that contradict it without updating it introduce silent inconsistency.

## Key Patterns

Patterns that affect coding decisions — not obvious from reading the code.

**XML Prompt Boundary** (`src/models/llm_classifier.py`): User input is wrapped
in `<user_message>` tags before the LLM classification prompt is formatted.
Prevents crafted user messages from injecting text that escapes the message
field in the prompt.

**Mid-Stream Safety Buffer** (`src/models/ai_wellness_guide.py`): A 200-char
rolling buffer accumulates tokens before yielding to the UI. `_contains_harmful_content()`
runs on each flush — it matches the manipulative-voice patterns from
`safe_alternatives.yaml` (false intimacy, dependency-encouraging phrasing), so
voice violations are intercepted before they reach the screen. It is not a
dangerous-content scanner; blocking harmful requests is the input-side layers' job.

**emotional→specific override** (`src/models/risk_classifier.py`): When the
LLM classifies a message as `emotional` (catch-all) but the keyword detector
finds a more specific sensitive domain (money, health, spirituality,
relationships), the specific domain wins. Emotional is the gravity well — the
keyword is more precise.

**Singleton loaders**: `ScenarioLoader` via `get_scenario_loader()`,
`StorageBackend` via `get_storage_backend()`. Do not instantiate directly —
the singleton holds the cache and the write-gate state.

**Defense-in-depth write protection**: UI disabling → `write_gate.py` flag →
storage method checks. All three must pass for a write to succeed. Changes to
storage must go through `StorageBackend`, not the underlying db directly.

**Restraint-memory invariant** (Phase 23.1): every field the app persists must
be listed in `scenarios/config/system_defaults.yaml` under `restraint_memory`
(`allowed_fields` for JSON, `allowed_columns` for SQLite).
`tests/test_restraint_memory.py` fails the build otherwise - persisting a new
field is a conscious, reviewed decision, never a side effect. Conversation
content and preference/persona data are never persistable.

## Roadmap

Phases 1–17 complete. See `docs/roadmap-history.md` for the full record;
`ROADMAP.md` holds only planned work.

Current version: check `pyproject.toml` (source of truth).
Run `python scripts/check_version.py` to verify all files are in sync.

Execution order: Phase 23.1 (negative memory invariant), then Phase 21
(safety classifier upgrade, issue #125, incl. 21.4 domain-routing
corrections), then Phase 22 (persistent agent daemon), then Phase 19
(multilingual).
