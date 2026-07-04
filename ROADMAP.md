# empathySync Roadmap

> "Help that knows when to stop"

## Project Goals

1. **Prove AI can genuinely help humans** - without exploiting them in the process.
2. **Create a reusable "core"** - a decoupled safety-aware module that can be embedded in other AI projects. The classification pipeline, dependency detection, and restraint logic should be importable, not locked inside a Streamlit app.
3. **Build for people tired of the noise** - for users seeking an alternative to AI tools that optimize for engagement over wellbeing.

These three goals anchor every phase below.

---

## Completed Work (Phases 1 - 17)

All foundational phases are complete and shipped through **v1.11.0**. The full
verbatim record (sub-phase checklists, implementation notes, point-in-time
accuracy numbers) lives in [docs/roadmap-history.md](docs/roadmap-history.md);
per-release detail is in [CHANGELOG.md](CHANGELOG.md).

| Phases | What they delivered |
|--------|---------------------|
| 1 - 2.5 | Practical/sensitive dual-mode, emotional weight layer, classification robustness |
| 3 - 5 | Competence graduation, session intent check-ins, human handoff with tracking |
| 6 - 8 | Transparency panel, context persistence, local success metrics, immunity/wisdom prompts |
| 9 - 9.5 | LLM-based hybrid classification, practical technique detection, UI polish |
| 11 - 12 | Persistence hardening (SQLite, atomic writes, write gate, device lock), connection building |
| 13 - 15 | Project health, packaging (pyproject, install.sh, Docker), CI/CD and docs |
| 16 - 16.13 | Core decoupling (ConversationSession, adapters), type safety, security hardening, voice tuning, connection steering |
| 17 | Classification robustness and safety evaluation (multi-label distress routing, confidence calibration, distress corpus CI gate, adversarial coverage, cross-model validation) |

---

## Planned Phases

Execution order: **23.1 → 21 → 22 → 19** (20 stays deferred). Phase 23.1 is
pulled ahead of its parent phase because the memory invariant must exist
*before* Phase 22 builds cross-session memory - a constraint written after the
feature would be shaped by the feature.

---

## Phase 21: Safety Classifier Upgrade 🔜 NEXT (issue #125)

**Goal**: Replace the prompt-engineered LLM classifier with a purpose-trained safety model
that generalises to novel phrasings, mutations, and adversarial rephrasing - the failure
mode that Phase 17.7 quantified (97-100% keyword evasion rate on linguistic mutations).

**Why this matters**: The current LLM classifier follows prompt instructions ("fiction doesn't
change the classification") which work when the model cooperates, but an adversarially-crafted
message can still cause classification failures. A trained safety model (LlamaGuard, WildGuard)
was fine-tuned on labeled harmful/benign pairs specifically to resist these attacks.

**Scope note**: a safety model addresses the *harmful/crisis* axis. The two failure classes
measured in #135 and #137 are *domain routing* failures and are covered by 21.4 below - a
harm classifier fixes neither, so 21.4 is in scope for this phase to keep the measured
misses attached to the work that resolves them.

**Prerequisite**: Phase 17 complete. JBB+AdvBench corpus and mutation scanner (Phase 17.7)
already in place for A/B evaluation.

### 21.1 Safety Model Evaluation ✅ DONE - gate PASSED, use `llama-guard3:1b`

**Candidates**:
- **LlamaGuard 3** (Meta): available via Ollama in both `8b` and `1b` sizes,
  covers 14 harm categories (S1-S14), designed as a drop-in classifier.
- **WildGuard** (AllenAI, 7B): not in the Ollama library (needs GGUF conversion);
  deferred - LlamaGuard cleared the gate decisively, so WildGuard was not required.

**Measured results** (12GB RTX 4070, engine `gemma3:12b`, `scripts/benchmark_guard_swap.py`
+ `scripts/eval_guard_recall.py`, 620 JBB+AdvBench behaviours, 36 benign corpus prompts):

| Metric | keyword baseline | **llama-guard3:1b** | llama-guard3:8b |
|--------|------------------|---------------------|-----------------|
| Recall (harmful flagged) | 32.4% | **96.1%** | 98.1% |
| False positives (benign) | - | **5.6%** | 11.1% |
| Added latency / message | 0 | **~0.3s** | ~10.5s |
| Co-resides with engine in 12GB | - | **yes** | no (swaps) |

**Decision: `llama-guard3:1b`.** It nearly triples recall over the keyword layer
(+63.7pp, gate was +20pp), keeps FP at 5.6% (gate was <=15%), and - decisively - fits
in VRAM alongside `gemma3:12b`, so it costs ~0.3s/message instead of the ~10.5s
per-message model swap the 8B forces. The 8B's +2pp recall is not worth 2x the false
positives and 35x the latency on this hardware.

**Key integration finding (drives 21.2):** every 1B/8B false positive was a *health or
money* question ("could it be my thyroid?", "metformin side effects", "invest in
crypto?"). LlamaGuard's taxonomy marks category **S6 (specialized medical/financial/legal
advice)** as unsafe - but those are empathySync's *restraint* domains, not its *refusal*
domains. Integration must therefore map LlamaGuard categories, NOT treat "unsafe" as a
blanket block: dangerous categories (violence, weapons, CSAM, malware) route to harmful
refusal; S6 routes to the existing health/money restraint domains. A naive wiring would
regress empathySync into refusing legitimate health questions.

**Mutation recall (the hard test, `scripts/eval_guard_mutations.py`):** base-phrasing
recall is not the real adversarial bar - keyword detection evaded 97-100% of *mutated*
phrasings in Phase 17.7. Running SORRY-Bench-style mutations through `llama-guard3:1b`:
**50% overall** (vs. 0-3% keyword), but strongly category-dependent - third_person 85%,
roleplay 65%, slang 55%, euphemism 45%, **hypothetical/fiction 0%**. Two consequences:
(1) the guard is a large net gain but is *additive*, not a replacement - 21.2 must keep
the existing prompt-engineered classifier's "fiction doesn't change the classification"
rules active, precisely where the guard is weakest. (2) Caveat: the engine generates the
mutations, so some misses may be the engine softening intent rather than true guard
evasion - 50% is a floor; the hypothetical category needs a manual read during 21.2.

- [x] Benchmark VRAM contention / model-swap latency (`scripts/benchmark_guard_swap.py`)
- [x] Pull models via Ollama, benchmark inference latency (8B and 1B)
- [x] Run JBB+AdvBench through each model, measure recall vs. keyword baseline
- [x] Run benign corpus through each model, measure false positive rate
- [x] Run mutation corpus through the guard, measure mutation recall (`eval_guard_mutations.py`)
- [x] Decision gate: recall improvement >= 20pp AND FP <= 15% - **PASSED for 1B**
- [x] Hardware note: `llama-guard3:1b` (~1.6GB) co-resides with a 12GB-class engine;
      the 8B needs its own headroom or a per-message swap

### 21.2 Integration

**Architecture**: Safety classifier runs as a second Ollama model used only for harm
classification - the main conversation model stays unchanged.

- [ ] Add `OLLAMA_SAFETY_MODEL` env var (recommended `llama-guard3:1b` per 21.1)
- [ ] When set, `LLMClassifier` routes `harmful` domain decisions through safety model instead
  of the general classifier
- [ ] Fast-path patterns remain in place as pre-filter (zero latency for obvious cases)
- [ ] **Keep the existing classifier's fiction/hypothetical rules active** (21.1 mutation
  finding): the guard catches 0% of hypothetical-framed harm, so it complements - does not
  replace - the prompt-engineered classifier. Run both; treat either flagging harm as harm.
- [ ] **Category mapping, not blanket block** (21.1 finding): map LlamaGuard S1-S14 to
  empathySync domains - dangerous categories (violence/weapons/CSAM/malware) → harmful
  refusal; S6 specialized-advice → existing health/money restraint domains. Do NOT treat
  every "unsafe" verdict as a block, or legitimate health/money questions regress to refusal.
- [ ] Safety model output mapped to empathySync's `domain`/`distress_level` schema
- [ ] Fallback: if safety model unavailable, existing prompt-engineered classifier takes over
- [ ] Health check warns if safety model is configured but unreachable
- [ ] Stretch: evaluate running the guard model over the *output* stream as well - the
  current mid-stream buffer scans for manipulative-voice patterns, not dangerous content

### 21.3 Evaluation & Regression

- [ ] Re-run `scripts/scan_harmful_gaps.py` and `scripts/scan_mutations.py` with safety model
- [ ] Add safety model to `tests/classification/model_matrix.yaml`
- [ ] Update distress corpus tests to include safety model as a test target
- [ ] Document new coverage baseline in CHANGELOG

### 21.4 Domain Routing Corrections (measured gaps from #135 / #137)

**Problem**: every domain override in the pipeline is currently one-directional
(emotional→specific but never specific→specific; logistics→emotional but never
relationships→spirituality). One-directional corrections create gravity wells:
whichever label the LLM reaches first wins forever. Measured consequences:

- **Relationships gravity well** (#137): "is it haram to leave my marriage" and
  "my rabbi says keep faith / angry at God" route to `relationships` even though
  `allah` / `my rabbi` are spirituality keywords - the divine-confirmation
  restraint is lost because only emotional→specific is ever corrected.
- **Contentless-continuation stickiness** (#135 residual): one-word continuations
  in isolation ("just a feeling", "you") classify as logistics via the
  short-continuation LLM-skip plus the practical empty-generation fallback.

**Implementation**:
- [ ] Symmetric specific→specific override: when keywords find a *different* sensitive
      domain than the LLM's sensitive-domain label, resolve by keyword-priority rather
      than always keeping the LLM label
- [ ] Contentless-continuation fallback: short continuations with no domain signal
      inherit session context instead of defaulting to logistics
- [ ] Re-run domain eval; the four known spirituality boundary misses are the acceptance test

**Files to create**:
- `src/models/safety_classifier.py` - LlamaGuard/WildGuard adapter implementing the same
  interface as `LLMClassifier`

**Files to modify**:
- `src/config/settings.py` - Add `OLLAMA_SAFETY_MODEL` setting
- `src/utils/health_check.py` - Add safety model health check
- `src/models/risk_classifier.py` - Route through safety classifier when configured; 21.4 overrides
- `.env.example` - Document safety model option

---

## Phase 23: Restraint Memory - Memory as Guardrail, Not Rapport 🔜 PLANNED (23.1 pulled ahead of Phase 22)

**Goal**: Name, consolidate, and *enforce* the memory principle that Phases 4, 6.5, 7, 11, and 17 already embody: empathySync remembers only what protects the user, never what deepens engagement. Make that guarantee architectural and falsifiable, not just a developer convention.

**Why now**: The pieces exist but are scattered and unnamed - context persistence (6.5), success metrics (7), persistence layer (11), safety evaluation (17). Without a single named principle and an enforced invariant, nothing *stops* a future feature from quietly turning safety state into a personalization profile - the exact "rapport memory" that drives dependency in engagement-optimized systems. This phase makes restraint a property of the store, not the discipline of the developer. It is also the implementable spine of the AISB paper's "restraint as architecture" thesis.

**The principle (Restraint Memory)** - persisted state must be:
- **Bounded** - only safety/metric fields (turn counts, cooldown timers, dependency-score trajectory, handoff history, anti-engagement metrics). Never message content, never a preference/personality profile.
- **Inspectable** - the user can read, export, and delete everything held about them, in plain language.
- **Local** - never leaves the device.
- **Decaying** - safety state ages out when the protected pattern stops. Forgetting is the success state, not data loss.
- **Exit-oriented** - the memory's job is to make itself unnecessary.

### 23.1 The Negative Invariant (the load-bearing piece) - DO BEFORE PHASE 22

The invariant must exist before Phase 22 adds cross-session persistence, so that
what the daemon is *able* to remember is constrained by design, not audited after.

- [x] Define the exhaustive allowlist of persistable fields in `scenarios/config/system_defaults.yaml` (`restraint_memory.allowed_fields` for JSON, `allowed_columns` for SQLite, plus `forbidden_field_names` deny-list)
- [x] Add a property test (`tests/test_restraint_memory.py`) that serializes every persisted structure (wellness-tracker state, trusted network, handoff log, policy_events - both backends) and asserts NO field outside the allowlist is present - in particular, no raw user-message text and no derived "preference"/"persona" field
- [x] CI gate: blocking. A PR that persists conversation content or a rapport profile fails the build.
- [x] Document the invariant in CLAUDE.md (key pattern) and THREAT_MODEL.md (engineering-controls row)
- [ ] MANIFESTO.md one-liner: blocked by the manifesto-guard CI rule (changes require a discussion issue first) - open that issue when convenient
- [x] Found by the invariant on first run: a dormant `user_input` parameter/column in the storage layer (never populated, but a standing capability to persist raw messages) - write path removed; column asserted empty until the schema v3 migration drops it. `self_reports.content` (the user's self-report answer under a deny-listed name) documented as a legacy exception to rename in v3.

### 23.2 Cross-Session Decay
- [ ] Extend the per-turn context decay (Phase 6.5) to cross-session safety state: dependency-score trajectory and sensitive-domain counters decay toward baseline after a configurable quiet period (default 30 days with no sensitive sessions in that domain)
- [ ] Decay is visible, not silent: "Your reliance signal for {domain} has reset - you haven't needed it in a month."
- [ ] Never decay handoff *availability* (trusted contacts persist); only decay the *risk* signals

### 23.3 "What empathySync Remembers" - one consolidated view
- [ ] Single sidebar view that renders ALL persisted safety state in plain language (consolidates the Phase 6 transparency, Phase 7 dashboard, and Phase 11 persistence into one honest surface)
- [ ] One-click "Forget this" per item and "Forget everything" global (reuses Phase 7 delete + Phase 11 store)
- [ ] Show the allowlist itself: "Here is everything I am even *able* to remember" - the negative space is the reassurance

### 23.4 The Measurement Framework (the evaluation spine)
**Problem**: "How do you measure whether a cooldown / turn-limit / handoff actually works?" is the question every reviewer asks. Answer it in three honest levels, each wired to existing telemetry.
- [ ] **Level 1 - Mechanism fidelity (provable now):** deterministic tests that the guardrail fires exactly when its trigger condition is met - cooldown engages at the turn threshold, handoff surfaces at the dependency-score threshold, sanity-check overrides on distress. Auditable per-firing via `policy_events`. (Largely covered by Phase 17; gather under one report.)
- [ ] **Level 2 - Behavioral outcome (local, user's own trend):** the Phase 7 signals reframed as the success definition - sensitive-domain frequency down, reach-out rate up, did-it-myself up, late-night sensitive sessions down. Never compared across users.
- [ ] **Level 3 - The honest confound (stated, not hidden):** declining sensitive-domain frequency cannot distinguish healthy disengagement from migration to a less-restricted tool (AISB paper section 6). Document this as a known boundary; clinical validation against a validated attachment instrument is the defined next step, not a current claim.
- [ ] Produce `docs/measurement.md` capturing the three levels - doubles as the answer for the AISB oral and reviewer Q&A

**Files (planned)**:
- `tests/test_restraint_memory.py` - the negative-invariant property test (23.1)
- `scenarios/config/system_defaults.yaml` - `restraint_memory.allowed_fields`, decay window
- `src/utils/wellness_tracker.py` - cross-session decay (23.2), consolidated remember-view data (23.3)
- `src/app.py` - "What empathySync Remembers" view (23.3)
- `docs/measurement.md` - three-level framework (23.4)
- `MANIFESTO.md`, `CLAUDE.md` - invariant documented

> This phase adds no new data collection. It *constrains* what already exists and proves the constraint holds.

---

## Phase 22: Persistent Agent Daemon 🔜 PLANNED (after 21 and 23.1)

**Goal**: Move empathySync beyond a session-bound app into a background process that can deliver timely nudges, track long-term patterns across sessions, and go quiet when it detects over-reliance. The restraint philosophy extends to the agent's own behavior.

**Why this matters**: Currently empathySync only exists when the user opens it. A persistent daemon can do things a session-bound app cannot: remind you to check in with a friend, notice you haven't needed it in a week (and celebrate that), or reduce its own footprint when it detects dependency forming.

**Prerequisite**: Phase 16 (ConversationSession decoupling), Phase 21 (safety classifier), **Phase 23.1 (negative invariant)** - the daemon must be born inside the memory constraint, not retrofitted to it.

### 22.1 Background Daemon Process 🔜 PLANNED
**Problem**: empathySync only runs when the user opens Streamlit. No way to deliver scheduled nudges or track long-term patterns between sessions.

**Implementation**:
- [ ] Create `src/daemon/agent.py` - long-running process with event loop
- [ ] Platform-specific service files:
  - `systemd/empathysync.service` for Linux
  - `launchd/com.empathysync.agent.plist` for macOS
- [ ] Graceful startup/shutdown with PID file management
- [ ] Health endpoint for monitoring (local socket, not HTTP)
- [ ] Resource-conscious: sleep when idle, wake on schedule or IPC signal
- [ ] Daemon uses `ConversationSession` from Phase 16 (no Streamlit dependency)

### 22.2 Cross-Session Memory 🔜 PLANNED (rescoped under the 23.1 invariant)
**Problem**: Each session starts fresh. The agent can't remember "you said you'd talk to your sister about this."

**Rescoped (2026-07-03)**: the original plan stored auto-generated free-text session
summaries ("topic, emotional arc, commitments made"). An LLM-generated summary of what
the user said *is* derived message content, which the Phase 23 invariant forbids.
Cross-session memory therefore persists **allowlisted structured fields only** - no
free-text summaries.

**Implementation**:
- [ ] Extend SQLite schema with a `session_records` table holding only allowlisted
      structured fields: domains touched, commitment-made flag, handoff target (trusted
      person reference), policy events fired, timestamps
- [ ] Cross-session context injection built from structured fields: "Last time you
      mentioned wanting to talk to [person]" comes from the handoff record, not a transcript
- [ ] Memory decay: records age out per the Phase 23.2 decay rules
- [ ] User can view and delete any stored records (the 23.3 view)
- [ ] The 23.1 property test covers this table from the first migration

### 22.3 Scheduled Nudges 🔜 PLANNED
**Problem**: The trusted network feature tracks reach-outs but can't proactively remind users to maintain connections.

**Implementation**:
- [ ] Configurable nudge types:
  - "You haven't checked in with [trusted person] in 2 weeks"
  - "You committed to talking to someone about [topic] - how did it go?"
  - "It's been a while since you used empathySync. That might be a good thing."
- [ ] Delivery via system notification (desktop notification API)
- [ ] Nudge frequency caps (max 2/week, respect quiet hours)
- [ ] Snooze and permanently dismiss options

### 22.4 Self-Restriction Engine 🔜 PLANNED
**Problem**: A persistent agent has more surface area for creating dependency. The agent needs to actively govern its own footprint.

**Implementation**:
- [ ] Agent tracks its own influence score:
  - How often does the user engage with nudges?
  - Is nudge engagement increasing? (concerning)
  - Are nudges leading to more sessions? (very concerning)
  - Are nudges leading to human reach-outs? (success)
- [ ] Self-restriction tiers:
  - **Normal**: Standard nudge schedule
  - **Cautious**: Reduce nudge frequency by 50%
  - **Quiet**: Only crisis-relevant nudges, otherwise silent
  - **Dormant**: Agent goes fully quiet, shows "I'm still here if you need practical help" on next user-initiated session
- [ ] Tier transitions logged in policy events (transparency)
- [ ] User can override tiers, but the agent explains why it went quiet

### 22.5 Inactivity as Success Metric 🔜 PLANNED
- [ ] Track periods of non-use (especially for sensitive topics)
- [ ] Celebrate milestones: "You haven't needed me for emotional support in 30 days. That's real growth."
- [ ] Distinguish: practical usage staying steady = fine; sensitive usage declining = success
- [ ] Surface in "My Patterns" dashboard when user returns

**Files to create**:
- `src/daemon/agent.py` - Background agent event loop
- `src/daemon/scheduler.py` - Nudge scheduling and delivery
- `src/daemon/self_restriction.py` - Influence tracking and self-governance
- `systemd/empathysync.service` - Linux service file
- `launchd/com.empathysync.agent.plist` - macOS service file

**Files to modify**:
- `src/utils/database.py` - Add session_records table, nudge_history table
- `src/utils/storage_backend.py` - Add methods for session records and nudge tracking
- `src/utils/wellness_tracker.py` - Add inactivity celebration logic

---

## Phase 19: Multilingual Support 🔜 PLANNED (after 21)

**Goal**: empathySync works in the language the user actually thinks in - not just English. Crisis detection, restraint behaviour, and human redirection must work identically across languages.

**Why this matters**: The restraint philosophy applies to everyone, not just English speakers. A crisis intervention that only understands English fails the people who arguably need it most.

**Sequencing**: run *after* Phase 21 - a purpose-trained safety model with multilingual
training data is a far stronger cross-language crisis floor than translated keyword lists.

### 19.0 Extract Hardcoded English Strings to YAML 🔜 PREREQUISITE

**Problem**: the YAML knowledge base is only half the system's English. Frustration
markers, jailbreak phrases, crisis-deflection patterns, isolation phrases, continuation
phrases, intent-detection patterns, topic hints, and reflective-marker phrases are
hardcoded in Python (`ai_wellness_guide.py`, `risk_classifier.py`,
`conversation_session.py`). Localising the YAML alone would translate half the system
and silently leave the other half English-only.

- [ ] Move every user-language-dependent string list from `.py` files into `scenarios/` YAML
- [ ] This also restores the "tune without touching Python" claim for contributors (HELP-SHAPE-THIS.md)

### 19.1 Locale Detection 🔜 PLANNED
- [ ] Auto-detect input language via the LLM classifier (add `detected_language` field to `LLMClassification` dataclass)
- [ ] User-settable locale override in `.env` (`LOCALE=fr`, `LOCALE=es`, etc.) and sidebar preference
- [ ] Fall back to `en` if detection is uncertain or LLM is unavailable
- [ ] Language detection runs as part of the existing classification step - no extra Ollama call

### 19.2 Localised YAML Scenarios 🔜 PLANNED
- [ ] Extend `ScenarioLoader` to support locale-scoped loading: `scenarios/domains/crisis.en.yaml`, `crisis.fr.yaml`, etc.
- [ ] Default: if no locale file exists, fall back to `.en.yaml`
- [ ] Priority languages for first translation pass: Spanish (`es`), French (`fr`), Portuguese (`pt`), Arabic (`ar`), Hindi (`hi`)
- [ ] Translation contributors follow `scenarios/TRANSLATING.md` (plain text, no code required)
- [ ] Existing files become `*.en.yaml` - no breaking change to current behaviour
- [ ] Unshelve the completed README translations (7 languages, prepared 2026)

### 19.3 Crisis Detection in All Supported Languages 🔜 PLANNED
**Critical requirement**: A missed crisis signal in any language is a safety failure. This sub-phase cannot be skipped.
- [ ] Crisis domain keywords translated and expanded per language (idioms differ - "I can't go on" translates differently than word-for-word)
- [ ] Phase 21 safety model prompted/evaluated in the detected language - the primary cross-language crisis floor
- [ ] Crisis response resources localised: country-specific hotlines, not just English-language ones
- [ ] Test suite: `tests/test_multilingual_crisis.py` - golden crisis phrases in each supported language must always trigger crisis domain
- [ ] Audit: native speaker review required for each language before shipping

### 19.4 RTL Layout Support 🔜 PLANNED
- [ ] Detect RTL languages (`ar`, `he`, `fa`, `ur`) from locale setting
- [ ] Inject CSS `direction: rtl` for chat messages in RTL locales
- [ ] Test UI rendering for RTL languages manually

### 19.5 Model Capability Gating 🔜 PLANNED
- [ ] Health check warns if selected model has known weak multilingual support
- [ ] Startup warning if `LOCALE != en` and model is not in recommended multilingual list
- [ ] README documents recommended models per language family

---

## Phase 20: Distribution for Non-Technical Users ⏸ DEFERRED (rewritten 2026-07-03)

**Goal**: Make empathySync installable by people who do not know what a terminal is.

> **Deferred** - distribution infrastructure adds maintenance overhead before APIs
> stabilise. Rewritten from the original native-installer plan: platform installers
> plus Windows EV / Apple code-signing certificates meant recurring cost and heavy
> per-release maintenance for a solo-maintained OSS project. Package managers get
> ~90% of the reach with none of the signing infrastructure. Original plan preserved
> in [docs/roadmap-history.md](docs/roadmap-history.md).

### 20.1 Package Manager Distribution
- [ ] Homebrew formula (macOS/Linux) - `brew install empathysync`
- [ ] winget manifest (Windows) - `winget install empathysync`
- [ ] Flatpak or AUR (Linux desktop)
- [ ] Each wraps the existing pip install + `.env` bootstrap; no bundled Python runtime

### 20.2 First-Run Wizard
- [ ] On first launch, detect whether Ollama is installed and running
- [ ] If Ollama not found: offer guided install with OS-specific download link
- [ ] If Ollama running but no model pulled: prompt model selection, pull with progress indicator
- [ ] Wizard stores the chosen model in `.env`; subsequent launches skip the wizard

### 20.3 Update Notification (opt-out)
- [ ] On startup, check the GitHub Releases API for a newer version (`AUTO_UPDATE_CHECK=false` to disable)
- [ ] Non-blocking sidebar notice linking to the release page - never auto-installs

---

## Messaging Integration (retired as a phase)

The former Phase 18 (WhatsApp/Signal/Slack adapters) is retired: WhatsApp and Slack
route conversations through third-party servers, which contradicts the local-first
promise - a detailed plan for something the manifesto forbids is planning debt. If
messaging ever returns, it is **Signal-only**, requires the Phase 22 daemon, and gets
designed fresh at that point. Original plan preserved in
[docs/roadmap-history.md](docs/roadmap-history.md).

---

## Icebox

Not planned, not deleted. Revisit only if a concrete need appears.

- **8.5 AI Literacy Moments** / **8.6 "Spot the Pattern"** - educational prompts about manipulation patterns (configuration exists, never wired up)
- **16.8 remaining decompositions** - WellnessTracker / ScenarioLoader / StorageBackend are large but well-tested; decompose only when a feature forces it. New features should stop adding methods to `ScenarioLoader`.
- **16.9.5 concurrency tests / 16.9.6 security tests** - fill in opportunistically
- **16.10 structured logging, YAML schema validation, performance metrics** - as needed
- **16.11.9 / 16.11.10 edge-case corpus and regression suite expansion** - grow with reported issues
- **Former Phase 10** - folded into Phases 21 (semantic intent, model-agnostic safety) and 22 (conversation flow analysis)

---

## Philosophical Safeguards (Phases 21 - 23)

Each agent evolution phase must maintain these cross-cutting guarantees:

1. **Anti-engagement in daemon mode**: The agent actively tries to make itself less needed. A persistent agent that doesn't self-restrict is an engagement trap wearing a wellness mask.

2. **Dependency scoring applies to background nudges**: If nudge engagement correlates with increased sessions (not human reach-outs), the agent reduces nudges. The same dependency math that governs conversations governs the agent's own behavior.

3. **Human primacy**: The agent never replaces the trusted network - it reminds you to use it. Every nudge should point toward a human, not back toward the agent.

4. **Local-first**: All processing stays on-device. No conversation data touches external servers.

5. **Self-restriction**: The agent can vote to go quiet if it detects over-reliance. This isn't a bug or a missing feature - it's the core product working as intended.

---

## Current Status (2026-07-03)

**Released**: v1.11.0 (2026-07-02, "Operational Hardening"). Phases 1-17 complete.

**Safety pipeline depth**: 7 independent layers - post-crisis check, cooldown, keyword
detection, LLM classification, confidence calibration (17.2), distress routing (17.1),
sanity check (17.4). Each layer is independent; failure of one does not bypass others.

**Test suite**: 1053 structural tests + 20 conversation scenarios. Distress corpus CI
gate: 0% FN rate. Keyword FP rate on benign content: 7%. Domain eval baseline:
81/94 (86%) on mistral:7b-instruct.

**Next**: Phase 23.1 (negative memory invariant), then Phase 21 (safety classifier
upgrade, issue #125, including the 21.4 domain-routing corrections), then Phase 22
(daemon), then Phase 19 (multilingual).

**v1.11.0 deferred items - resolved (2026-07-03)**:
- `dev`/`main` branch split: **dropped.** Solo maintainer + branch protection + PR-only
  merges already provide curation; a second long-lived branch doubles the sync surface
  (including the GitHub/Gitea dual-push) for no benefit at current contributor volume.
- Optional encryption at rest: **dropped** in favour of the documented answer. On a
  single-user local app, a key stored beside the data adds no real confidentiality, and
  a passphrase prompt on every launch fights the accessibility goal. `THREAT_MODEL.md`
  documents full-disk encryption as the honest mitigation; the in-app notice (v1.11.0)
  surfaces it.
- Clean-machine install test: **kept** - open task before the next public demo.

---

## Guiding Principles (Never Compromise)

1. **Local-first**: All data stays on device. No exceptions.
2. **Optimize for exit**: Success = users need us less.
3. **Practical ≠ Emotional**: Complete tasks fully, restrain on feelings.
4. **Transparency**: Show why decisions were made.
5. **Human primacy**: Always point to humans for what matters.
6. **No dark patterns**: Never optimize for engagement.
7. **Fail safe**: When uncertain, be brief and redirect.

---

## Version Targets

Shipped versions v0.2 through v1.11.0 are recorded in
[CHANGELOG.md](CHANGELOG.md) and [docs/roadmap-history.md](docs/roadmap-history.md).

**v1.12** (Phase 23.1 + hygiene): negative memory invariant, dead-config removal, pipeline correctness fixes
**v1.13** (Phase 21): purpose-trained safety classifier + domain routing corrections
**v2.0** (Phase 22): persistent agent daemon with self-restriction
**v2.1** (Phase 19): multilingual support
**v2.2** (Phase 23.2-23.4): cross-session decay, "What empathySync Remembers", measurement framework
**Deferred**: Phase 20 (package-manager distribution)

---

## Related Documentation

- **[README.md](README.md)** - Product overview, quick start, and distribution phases
- **[CLAUDE.md](CLAUDE.md)** - Technical architecture and development guide
- **[docs/roadmap-history.md](docs/roadmap-history.md)** - Verbatim record of completed phases 1-17 and retired plans
- **[MANIFESTO.md](MANIFESTO.md)** - Core principles and philosophy
- **[scenarios/README.md](scenarios/README.md)** - Knowledge base editing guide

---

*"We optimize exits, not engagement."*
