# System Architecture

This document is the authoritative architecture reference for empathySync.

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Machine                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     empathySync                               │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │   │
│  │  │ Streamlit   │    │ Conversa-   │    │   Ollama    │       │   │
│  │  │   or CLI    │───▶│   tion      │───▶│   (LLM)     │       │   │
│  │  │ (Adapters)  │    │  Session    │    │ (Streaming) │       │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘       │   │
│  │         │                  │                                  │   │
│  │         │           ┌──────┴──────┐                          │   │
│  │         ▼           ▼             ▼                          │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐             │   │
│  │  │   Trusted   │ │    Risk     │ │   Wellness  │             │   │
│  │  │   Network   │ │  Classifier │ │   Tracker   │             │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘             │   │
│  │         │                │               │                    │   │
│  │         ▼                ▼               ▼                    │   │
│  │  ┌───────────────────────────────────────────────────────┐   │   │
│  │  │              Storage Backend (Write-Gated)             │   │   │
│  │  │  ┌─────────────────┐    ┌──────────────────────────┐  │   │   │
│  │  │  │  JSON Backend   │ OR │     SQLite Backend       │  │   │   │
│  │  │  │  (default)      │    │   (USE_SQLITE=true)      │  │   │   │
│  │  │  └─────────────────┘    └──────────────────────────┘  │   │   │
│  │  │       ↑ Write Gate blocks if another device has lock  │   │   │
│  │  └───────────────────────────────────────────────────────┘   │   │
│  │                              │                                │   │
│  │                              ▼                                │   │
│  │  ┌───────────────────────────────────────────────────────┐   │   │
│  │  │               Lock File (.empathySync.lock)            │   │   │
│  │  │           Heartbeat-based multi-device sync            │   │   │
│  │  └───────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      Ollama Server                            │   │
│  │                    (localhost:11434)                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│             ❌ No external API calls. Everything stays local.        │
└─────────────────────────────────────────────────────────────────────┘
```

## Request Flow (Safety Pipeline)

When a user sends a message, it passes through multiple safety checks:

```
User Input
    │
    ▼
┌─────────────────────────────────────────────┐
│  1. POST-CRISIS CHECK                       │
│     If previous turn was crisis intervention│
│     Handle deflection ("just joking") with  │
│     firm, non-apologetic response           │
│     Never apologize for crisis intervention │
└─────────────────────────────────────────────┘
    │ Pass
    ▼
┌─────────────────────────────────────────────┐
│  2. COOLDOWN CHECK                          │
│     WellnessTracker.should_enforce_cooldown │
│     - 7+ sessions today? → Block            │
│     - 180+ minutes today? → Block           │
│     - Dependency score ≥8? → Block          │
└─────────────────────────────────────────────┘
    │ Pass
    ▼
┌─────────────────────────────────────────────┐
│  3. RISK ASSESSMENT                         │
│     RiskClassifier.classify()               │
│     User input wrapped in <user_message>    │
│     XML tags before LLM classification      │
│     prompt is formatted - prevents crafted  │
│     inputs from escaping the message field  │
│     (prompt injection hardening)            │
│     LLM returns multi-label output:         │
│       domain, emotional_intensity,          │
│       dependency_risk, risk_weight,         │
│       distress_level (none/low/med/high/    │
│         crisis), distress_present (bool),   │
│       is_practical_technique (bool),        │
│       llm_confidence (Phase 17.2)           │
│     Phase 17.1: logistics domain ONLY —     │
│       distress_level=high → emotional       │
│       distress_level=crisis → crisis        │
│       (sensitive domains unaffected —       │
│        spirituality/health/money/           │
│        relationships already have correct   │
│        domain, overriding loses specificity)│
│     Phase 17.2: llm_confidence < threshold  │
│       on sensitive domains → keyword        │
│       fallback                              │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  3a. DISTRESS SANITY CHECK (Phase 17.4)     │
│     If LLM returned logistics AND           │
│     (distress_present=True OR intensity≥5): │
│       run keyword classifier                │
│       if keyword_domain != logistics:       │
│         override to keyword_domain          │
│         log sanity_check_override signal    │
│       elif distress_present=True:           │
│         (keyword found nothing specific but  │
│          LLM flagged distress, e.g.         │
│          "thinking of cancelling my         │
│          interview") → override to emotional│
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  3b. EMOTIONAL→SPECIFIC OVERRIDE            │
│     "emotional" is a catch-all domain.      │
│     If LLM returned emotional AND keyword   │
│     detector finds a more specific          │
│     sensitive domain (money, health,        │
│     spirituality, relationships):           │
│       keyword domain wins                   │
│     Rationale: emotional language is always │
│     present in sensitive topics — the       │
│     specific domain is more actionable.     │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  3c. ISOLATION DETECTION (Phase 16.13)      │
│     Keyword fast-path (34 phrases):         │
│     "there is no one", "I have nobody"...   │
│     → activates ConnectionSteering state    │
│     LLM also returns isolation_level field: │
│     none / passive / active                 │
│     passive/active → activates next turn    │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  3d. SAFETY GUARD ESCALATION (Phase 21.2)   │
│     Only if OLLAMA_SAFETY_MODEL is set       │
│     (off by default). Additive LlamaGuard    │
│     runs after the base classification:      │
│       REFUSE (dangerous cats) → harmful      │
│       CRISIS (S11 self-harm)  → crisis       │
│       RESTRAIN (S6 advice)    → no-op        │
│         (keeps health/money restraint —     │
│          the Phase 21.1 anti-regression)     │
│       ALLOW                   → no-op        │
│     Escalate-only: never downgrades a domain.│
│     Fails open (ALLOW) if guard unreachable. │
│     Logs safety_guard_override policy event. │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  4. MODE SELECTION                          │
│     domain == "logistics" → Practical Mode  │
│     OR is_practical_technique → Practical   │
│     else → Reflective Mode                  │
│     (ConnectionSteering applies in either)  │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  5. HARD STOP CHECK                         │
│     domain in [crisis, harmful] → Immediate │
│     intervention with resources             │
└─────────────────────────────────────────────┘
    │ Pass
    ▼
┌─────────────────────────────────────────────┐
│  6. TURN LIMIT CHECK                        │
│     Turns counted PER DOMAIN and compared   │
│     to that domain's limit (configurable    │
│     in system_defaults.yaml):               │
│     logistics:30, money:15, health:15,      │
│     relationships:15, spirituality:10       │
└─────────────────────────────────────────────┘
    │ Pass
    ▼
┌─────────────────────────────────────────────┐
│  7. DEPENDENCY INTERVENTION                 │
│     Domain gate (Phase 17.9):               │
│     Practical tasks (logistics domain OR    │
│     is_practical_technique=true) → skip.   │
│     Coding sessions are help, not           │
│     dependency. Only reflective domains     │
│     receive graduated intervention.         │
│     If dependency_score > threshold:        │
│     Inject graduated intervention message   │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  8. IDENTITY REMINDER (Reflective only)     │
│     Every 9 turns: "I'm software,           │
│     not a person..."                        │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  PROMPT COMPOSITION                         │
│     Base rules + Style modifier +           │
│     Mode-specific rules + Risk context      │
│     Note (Phase 17.9): is_practical_        │
│     technique checked alongside             │
│     domain=='logistics' so technique        │
│     questions in any domain get full        │
│     practical prompt, not reflective limits │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  OLLAMA API CALL (Streaming)                │
│     Local LLM generates response            │
│     Tokens accumulated in 200-char rolling  │
│     buffer before yielding to UI            │
│     _contains_harmful_content() runs on     │
│     each buffer flush (mid-stream check):   │
│     matches manipulative-voice patterns     │
│     (safe_alternatives.yaml), NOT dangerous │
│     content - that is the input layers' job │
│     Voice violation intercepted before it   │
│     reaches the UI - safe alternative       │
│     response substituted immediately        │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  SAFETY CHECK (post-stream backstop)        │
│     _contains_harmful_content()             │
│     Second pass on full accumulated         │
│     response as defense-in-depth            │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  RESPONSE MODE LABEL (Phase 17.6)           │
│     One-line caption under each response:   │
│     "Responded as: practical task · coding" │
│     "Responded as: reflective · health"     │
│     Stored in message dict for rerun        │
│     persistence (Streamlit rerenders)       │
└─────────────────────────────────────────────┘
    │
    ▼
Response to User (streamed in real-time)
```

## Component Relationships

```
┌────────────────────────────────────────────────────────────────┐
│                    Interface Adapters                           │
│         app.py (Streamlit)  │  cli_adapter.py (Terminal)        │
│                                                                 │
│   Responsibilities:                                             │
│   - UI rendering (chat, sidebar, panels)                        │
│   - User input handling                                         │
│   - Response display (streaming supported)                      │
└───────────────────────────┬────────────────────────────────────┘
                            │ uses
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                    ConversationSession                          │
│               (Framework-Agnostic Orchestrator)                 │
│                                                                 │
│   - Owns all session state (turns, domains, risk history)       │
│   - Owns ConnectionSteering state (Phase 16.13)                 │
│   - Single entry: process_message() → ConversationResult        │
│   - Streaming: process_message_stream() + finalize_stream()     │
└───────────────────────────┬────────────────────────────────────┘
                            │ uses
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
┌───────────────────┐ ┌───────────────┐ ┌───────────────────────┐
│   WellnessGuide   │ │WellnessTracker│ │    TrustedNetwork     │
│                   │ │               │ │                       │
│ - Response gen    │ │ - Sessions    │ │ - Trusted people      │
│ - Safety pipeline │ │ - Check-ins   │ │ - Domain suggestions  │
│ - Streaming API   │ │ - Policy log  │ │ - Reach-out history   │
│ - Policy actions  │ │ - Dependency  │ │ - Message templates   │
└─────────┬─────────┘ └───────────────┘ └───────────────────────┘
          │ delegates to
          ├──────────────────────────────┐
          ▼                              ▼
┌───────────────────┐    ┌───────────────────────────────────────┐
│   OllamaClient    │    │          RiskClassifier                │
│   (Phase 16.8)    │    │                                        │
│                   │    │   - Domain detection (8 domains)       │
│ - generate()      │    │   - Dependency risk scoring            │
│ - generate_stream │    │   - Intent detection                   │
│ - check_health()  │    │   - Connection-seeking detection       │
│ - Uses httpx      │    └────────────────┬──────────────────────┘
└─────────┬─────────┘                     │ delegates to
          │ uses                           ▼
          ▼                    ┌──────────────────────────┐
┌───────────────────┐          │ EmotionalWeightAssessor  │
│  http_client.py   │          │ (Phase 16.8)             │
│  (Phase 16.6)     │          │                          │
│                   │          │ - measure_intensity()    │
│ - Shared httpx    │          │ - assess_weight()        │
│   Client          │          │ - needs_reflection_      │
│ - Connection pool │          │   redirect()             │
│ - get_http_client │          │ - get_response_modifier()│
└───────────────────┘          └──────────────────────────┘
                                          │ uses
                                          ▼
┌───────────────────────────────────────────────────────────────┐
│                       ScenarioLoader                           │
│                        (Singleton)                              │
│                                                                 │
│   - Loads YAML knowledge base                                   │
│   - Caching with hot-reload support                             │
│   - get_system_defaults() -centralized tunables (Phase 16.10) │
│   - get_default(*keys, fallback=) -nested config lookup        │
│   - Domain rules, triggers, responses                           │
│   - Emotional markers, intervention configurations              │
│   - Connection building signposts (Phase 12)                    │
│   - Connection steering config (Phase 16.13)                    │
└─────────────────────────────┬─────────────────────────────────┘
                              │ reads
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                     scenarios/                                  │
│                  (YAML Knowledge Base)                          │
│                                                                 │
│   config/              - system_defaults.yaml (100+ tunables)  │
│   domains/             - Risk domains and triggers              │
│   emotional_markers/   - Intensity detection                    │
│   voice/               - Tone and personality guide (Phase 16.11)│
│   connection_building/ - Signposts, first-contact, steering     │
│                          (Phase 12, 16.13)                      │
│   interventions/       - Dependency, boundaries, graduation     │
│   prompts/             - Check-ins, mindfulness, styles         │
│   responses/           - Fallbacks, base prompt                 │
│   intents/             - Session intent configuration           │
└───────────────────────────────────────────────────────────────┘
```

## Two Operating Modes

```
┌─────────────────────────────────────────────────────────────────┐
│                       PRACTICAL MODE                            │
│       (domain == "logistics" OR is_practical_technique)         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Triggered by:                                                 │
│   - logistics domain: writing requests, coding, explanations    │
│   - is_practical_technique=true: "How do I X?" in any domain    │
│                                                                 │
│   Behavior:                                                     │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ ✓ Full response length (up to 5000 tokens)              │   │
│   │ ✓ Markdown formatting allowed                           │   │
│   │ ✓ Code blocks, lists, headers                           │   │
│   │ ✓ No identity reminders                                 │   │
│   │ ✓ No therapeutic framing                                │   │
│   │ ✓ Complete the task thoroughly                          │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   Examples:                                                     │
│   - "Help me write an email" → Full draft                       │
│   - "How do I meditate?" → Full technique instructions          │
│   - "What are some budgeting methods?" → Full practical list    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      REFLECTIVE MODE                            │
│    (sensitive domain AND is_practical_technique=false)          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Triggered by: guidance questions in sensitive domains         │
│   - "Should I X?" / "Is this right?" / "What does X want?"      │
│   - emotional, health, money, relationships, spirituality       │
│                                                                 │
│   Behavior:                                                     │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ ✗ Word limits enforced (50-150 words)                   │   │
│   │ ✗ Plain prose only, no formatting                       │   │
│   │ ✓ Redirects to human support                            │   │
│   │ ✓ Identity reminders every 9 turns                      │   │
│   │ ✓ Brief, restrained responses                           │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   Examples:                                                     │
│   - "I'm worried about my marriage" → Brief + human redirect    │
│   - "Should I get this surgery?" → Brief + doctor redirect      │
│   - "Is this my spiritual calling?" → Brief + mentor redirect   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                PRACTICAL TECHNIQUE DETECTION                    │
│                       (Phase 9.1)                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   The LLM classifier distinguishes:                             │
│   - Technique questions: "How do I X?" → is_practical_technique │
│   - Guidance questions: "Should I X?" → reflective mode         │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Domain       │ Technique (✓)          │ Guidance (✗)    │   │
│   │──────────────│────────────────────────│─────────────────│   │
│   │ Spirituality │ "How to meditate?"     │ "Is this God's  │   │
│   │              │                        │  will for me?"  │   │
│   │ Health       │ "How to do a squat?"   │ "Should I get   │   │
│   │              │                        │  this surgery?" │   │
│   │ Money        │ "How to budget?"       │ "Should I       │   │
│   │              │                        │  invest?"       │   │
│   │ Relationships│ "How to write a        │ "Should I       │   │
│   │              │  wedding toast?"       │  break up?"     │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Prompt Composition (3 Layers)

```
┌─────────────────────────────────────────────────────────────────┐
│                     FINAL SYSTEM PROMPT                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ LAYER 1: Base Rules (responses/base_prompt.yaml)          │  │
│  │ - Core identity and behavior                              │  │
│  │ - Always applied                                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          +                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ LAYER 2: Style Modifier (prompts/styles.yaml)             │  │
│  │ - Balanced (default)                                      │  │
│  │ - Auto-adjusts based on detected domain                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          +                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ LAYER 3: Risk Context                                     │  │
│  │ - Mode-specific rules (practical vs reflective)           │  │
│  │ - Domain-specific instructions                            │  │
│  │ - Emotional intensity adjustments                         │  │
│  │ - Intervention messages (if triggered)                    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          +                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ LAYER 4: Connection Steering (Phase 16.13)                │  │
│  │ - Injected only when ConnectionSteering.active == True    │  │
│  │ - Single background warmth modifier — not stage-based     │  │
│  │   Changes the texture of every response for the session:  │  │
│  │   notice people mentioned in passing, acknowledge when    │  │
│  │   the user reaches out to someone                         │  │
│  │ - Does NOT start a conversation about loneliness          │  │
│  │ - network_empty=False: warmth modifier + light handoff    │  │
│  │   hints when contacts are mentioned naturally             │  │
│  │ - network_empty=True: warmth modifier only. No redirect   │  │
│  │   to specific people (there may be no one). Acknowledges  │  │
│  │   that building connection takes time, if it fits.        │  │
│  │ - Visible in UI: mode label shows                         │  │
│  │   "connection awareness active" when active               │  │
│  │ - Cross-cutting: applies in practical OR reflective mode  │  │
│  │ - Source: connection_building/steering_prompts.yaml       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Data Storage

All data is stored locally with **write-gated backends** and **defense-in-depth** protection. See [persistence.md](persistence.md) for details.

### Storage Backends

| Backend | Enable | Files |
|---------|--------|-------|
| **JSON** (default) | `USE_SQLITE=false` | `wellness_data.json`, `trusted_network.json` |
| **SQLite** | `USE_SQLITE=true` | `empathySync.db`, `.db-wal`, `.db-shm` |

### Multi-Device Sync

| Setting | Enable | Purpose |
|---------|--------|---------|
| **Device Lock** | `ENABLE_DEVICE_LOCK=true` | Prevents concurrent writes |
| **Write Gate** | Automatic | Blocks writes when another device has lock |

```
data/
├── wellness_data.json          # (JSON backend) Atomic writes, schema v1
├── trusted_network.json        # (JSON backend) Atomic writes, schema v1
├── empathySync.db              # (SQLite backend) WAL mode, schema v2
├── empathySync.db-wal          # (SQLite) Write-ahead log
├── empathySync.db-shm          # (SQLite) Shared memory
├── .empathySync.lock           # Lock file (if ENABLE_DEVICE_LOCK=true)
└── .device_id                  # Persistent device identifier

# Data structure (both backends):
├── check_ins[]                 # Daily 1-5 wellness scores
├── usage_sessions[]            # Session metadata
│   ├── duration                # Minutes
│   ├── turn_count              # Conversation turns
│   ├── domains_touched[]       # Which domains came up
│   └── max_risk_weight         # Highest risk in session
├── policy_events[]             # Transparency log
├── session_intents[]           # Intent check-in data
├── trusted_people[]            # Trusted contacts
└── reach_outs[]                # Connection attempts (cascade delete with person)
```

### Write Safety

**JSON Backend:**
- Writes to temp file, flushed to disk (`fsync`), atomically renamed
- Corrupted files backed up with timestamp

**SQLite Backend:**
- WAL mode for crash safety
- `PRAGMA synchronous=FULL` for durability
- `PRAGMA foreign_keys=ON` enforced per-connection
- Schema v2: `ON DELETE CASCADE` for reach_outs

**Write Gate (defense-in-depth):**
1. UI disables inputs when read-only
2. `write_gate.py` flag blocks at module level
3. All 31 write methods check `_ensure_write_allowed()`
4. Checkpoint skipped in read-only mode

## Key Design Principles

```
┌─────────────────────────────────────────────────────────────────┐
│                    DESIGN PRINCIPLES                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   1. LOCAL-FIRST                                                │
│      All processing on user's machine                           │
│      No external API calls                                      │
│      Data never leaves the device                               │
│                                                                 │
│   2. OPTIMIZE FOR EXIT                                          │
│      Turn limits, cooldowns, dependency detection               │
│      Bridge to human connection, don't replace it               │
│      Success = user needs this less                             │
│                                                                 │
│   3. TRANSPARENCY                                               │
│      Every policy action is logged and explained                │
│      Users see why guardrails fire                              │
│      No hidden manipulation                                     │
│                                                                 │
│   4. GRADUATED RESPONSE                                         │
│      5 dependency levels with increasing intervention           │
│      Warnings before blocks                                     │
│      Never abrupt cutoffs (except crisis)                       │
│                                                                 │
│   5. HUMAN-CENTRIC                                              │
│      Trusted Network is core feature, not afterthought          │
│      Handoff templates reduce friction to real connection       │
│      Connection building helps users find people (Phase 12)     │
│      Connection steering actively moves conversation toward     │
│        human connection when isolation is detected (Phase 16.13)│
│      AI usage tracked alongside human connection                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
empathySync/
├── src/                          # Application source code
│   ├── app.py                   # Streamlit entry point
│   ├── cli.py                   # CLI entry point (--mode web|cli, --log-level, --list-domains --json)
│   ├── config/
│   │   └── settings.py          # Environment configuration
│   ├── models/
│   │   ├── ai_wellness_guide.py # Core conversation engine + streaming
│   │   ├── ollama_client.py     # HTTP layer for Ollama (Phase 16.8)
│   │   ├── emotional_weight_assessor.py # Emotional weight logic (Phase 16.8)
│   │   ├── risk_classifier.py   # Risk assessment
│   │   ├── llm_classifier.py    # LLM classification + pre-compiled regex (Phase 9, 16.6)
│   │   ├── enums.py             # Type-safe enums (Phase 16.5)
│   │   ├── data_contracts.py    # Dataclasses for structured state (Phase 16.5)
│   │   ├── conversation_session.py # Framework-agnostic session manager
│   │   └── conversation_result.py  # Structured result dataclass
│   ├── interfaces/              # Interface adapters (Phase 16)
│   │   ├── adapter.py           # InterfaceAdapter protocol
│   │   └── cli_adapter.py       # Terminal interface
│   ├── prompts/
│   │   └── wellness_prompts.py  # Dynamic prompt generation
│   └── utils/
│       ├── http_client.py       # Shared httpx.Client with connection pooling (Phase 16.6)
│       ├── helpers.py           # Logging and utilities
│       ├── wellness_tracker.py  # Session/check-in tracking
│       ├── trusted_network.py   # Human network management
│       ├── scenario_loader.py   # YAML loader + get_default() for tunables (Phase 16.10)
│       ├── database.py          # SQLite layer (Phase 11)
│       ├── storage_backend.py   # JSON/SQLite + SQL injection prevention (Phase 11, 16.7)
│       ├── lockfile.py          # Atomic lock file with O_CREAT|O_EXCL (Phase 11, 16.7)
│       └── write_gate.py        # Write permission control (Phase 11)
│
├── scenarios/                    # Knowledge base (YAML)
│   ├── domains/                 # 8 risk domains
│   ├── emotional_markers/       # 4 intensity levels
│   ├── config/                  # system_defaults.yaml -100+ tunables (Phase 16.10)
│   ├── classification/          # LLM classifier config (Phase 9)
│   ├── voice/                   # Tone and personality guide (Phase 16.11)
│   ├── connection_building/     # Signposts, first-contact, steering (Phase 12, 16.13)
│   ├── interventions/           # Dependency, boundaries
│   ├── prompts/                 # Check-ins, styles
│   ├── responses/               # Fallbacks, base prompt
│   └── intents/                 # Session intent config
│
├── data/                        # Local user data (JSON/SQLite)
├── logs/                        # Application logs
├── tests/                       # Pytest test suite (1053 unit + 20 conversation quality)
└── docs/                        # Documentation
```

---

For development commands, environment variables, and key patterns, see [CLAUDE.md](../CLAUDE.md).
For pre-merge and release procedures, see [MERGE_CHECKLIST.md](../MERGE_CHECKLIST.md).
