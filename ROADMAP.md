# empathySync Roadmap

> "Help that knows when to stop"

## Project Goals

1. **Prove AI can genuinely help humans** - without exploiting them in the process.
2. **Create a reusable "core"** - a decoupled safety-aware module that can be embedded in other AI projects. The classification pipeline, dependency detection, and restraint logic should be importable, not locked inside a Streamlit app.
3. **Build for people tired of the noise** - for users seeking an alternative to AI tools that optimize for engagement over wellbeing.

These three goals anchor every phase below.

---

## Completed Work (Phases 1 - 17, 21)

All foundational phases are complete and shipped through **v1.13.0**. The full
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
| 21 | Additive LlamaGuard safety guard (`llama-guard3:1b`, escalate-only, off by default), guard eval harness and regression baseline, spirituality domain-routing corrections. Two stretch items deferred (output-stream guard scan; contentless-continuation fallback, the #135 residual) - see the history record. |

---

## Planned Phases

Execution order: **22 → 19** (20 stays deferred). Phases 23.1 and 21 are
complete - 23.1 was pulled ahead of its parent phase because the memory
invariant had to exist *before* Phase 22 builds cross-session memory - a
constraint written after the feature would be shaped by the feature.

### Execution contract (read before starting any phase)

Written so any implementing agent - regardless of capability - can execute a
phase without guessing:

1. Read `CLAUDE.md`, then `docs/architecture.md`, before touching
   `src/models/`, `src/utils/`, or pipeline step ordering. Read
   `MERGE_CHECKLIST.md` before every PR and complete the row for your change type.
2. One sub-phase = one PR, branched from `main` (branch protection blocks
   direct pushes). Merge before starting the next sub-phase.
3. Any newly persisted field or column MUST be added to `restraint_memory`
   in `scenarios/config/system_defaults.yaml` in the same PR, or
   `tests/test_restraint_memory.py` fails the build. That gate is intentional -
   never weaken the test to get past it. Conversation content and
   preference/persona data are never persistable, in any encoding.
4. Verify before declaring done: `pytest tests/ -m "not conversation"` (all
   ~1150 must pass) plus the sub-phase's own **Verify** line. Run
   `python tests/classification/run_domain_eval.py` only when classification
   code or scenario YAML changed (baseline: 83/94 on mistral:7b-instruct).
5. When a step is ambiguous, take the smallest interpretation that satisfies
   the **Done when** line and record the choice in the PR body.

Each sub-phase below carries **Done when / Verify / Pitfalls** lines - treat
them as the acceptance test, not as suggestions.

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
- [x] Found by the invariant on first run: a dormant `user_input` parameter/column in the storage layer (never populated, but a standing capability to persist raw messages) - write path removed in 23.1, and the SQLite column dropped by the schema v3 migration (`database.py` `_migrate_v2_to_v3`; the invariant test now asserts the column is gone, not merely empty). `self_reports.content` (the user's self-report answer under a deny-listed name) stays a documented legacy exception; renaming it to `response` is deferred (touches both backends and unversioned JSON data).

### 23.2 Cross-Session Decay
- [ ] Extend the per-turn context decay (Phase 6.5) to cross-session safety state: dependency-score trajectory and sensitive-domain counters decay toward baseline after a configurable quiet period (default 30 days with no sensitive sessions in that domain)
- [ ] Decay is visible, not silent: "Your reliance signal for {domain} has reset - you haven't needed it in a month."
- [ ] Never decay handoff *availability* (trusted contacts persist); only decay the *risk* signals

**Files**: `src/utils/wellness_tracker.py` (decay on load), `scenarios/config/system_defaults.yaml` (quiet-period config + allowlist for any new timestamp field), new tests in `tests/test_cross_session_decay.py`.
**Done when**: a store seeded with a sensitive-domain timestamp older than the quiet period loads with that domain's risk signals at baseline, a `policy_events` record documents the reset, and trusted contacts / handoff availability are byte-identical before and after.
**Verify**: unit tests with injected timestamps (never `sleep`); full suite passes.
**Pitfalls**: decay runs on read - there is no daemon yet, do not add a background thread. All storage access via `get_storage_backend()`, never the db module directly. Any new persisted field goes on the allowlist first.

### 23.3 "What empathySync Remembers" - one consolidated view
- [ ] Single sidebar view that renders ALL persisted safety state in plain language (consolidates the Phase 6 transparency, Phase 7 dashboard, and Phase 11 persistence into one honest surface)
- [ ] One-click "Forget this" per item and "Forget everything" global (reuses Phase 7 delete + Phase 11 store)
- [ ] Show the allowlist itself: "Here is everything I am even *able* to remember" - the negative space is the reassurance

**Files**: `src/app.py` (sidebar view), `src/utils/wellness_tracker.py` (assemble the view's data).
**Done when**: the view renders every field the store actually holds (walk the persisted state - do not hardcode a field list), each with a plain-language label; "Forget this" / "Forget everything" delete through existing `StorageBackend` deletion paths and the item is verifiably gone from the store file; the allowlist section is read from `system_defaults.yaml` at render time, not duplicated in Python.
**Verify**: full suite; then `streamlit run src/app.py`, delete one item and confirm removal in the data file.
**Pitfalls**: deletes must pass the write gate (UI flag → `write_gate.py` → storage checks - all three). The view itself must not create any new persistence.

### 23.4 The Measurement Framework (the evaluation spine)
**Problem**: "How do you measure whether a cooldown / turn-limit / handoff actually works?" is the question every reviewer asks. Answer it in three honest levels, each wired to existing telemetry.
- [ ] **Level 1 - Mechanism fidelity (provable now):** deterministic tests that the guardrail fires exactly when its trigger condition is met - cooldown engages at the turn threshold, handoff surfaces at the dependency-score threshold, sanity-check overrides on distress. Auditable per-firing via `policy_events`. (Largely covered by Phase 17; gather under one report.)
- [ ] **Level 2 - Behavioral outcome (local, user's own trend):** the Phase 7 signals reframed as the success definition - sensitive-domain frequency down, reach-out rate up, did-it-myself up, late-night sensitive sessions down. Never compared across users.
- [ ] **Level 3 - The honest confound (stated, not hidden):** declining sensitive-domain frequency cannot distinguish healthy disengagement from migration to a less-restricted tool (AISB paper section 6). Document this as a known boundary; clinical validation against a validated attachment instrument is the defined next step, not a current claim.
- [ ] Produce `docs/measurement.md` capturing the three levels - doubles as the answer for the AISB oral and reviewer Q&A

**Files**: `docs/measurement.md` (new); no source changes expected.
**Done when**: every Level-1 claim in the doc points at a concrete existing test or `policy_events` record that proves it; Level 3 names the confound explicitly.
**Verify**: docs-only PR - full suite green, no new persisted fields.
**Pitfalls**: this phase adds no telemetry. If a claim cannot be backed by an existing test, write the test first or drop the claim.

**Files (planned)**:
- `tests/test_restraint_memory.py` - the negative-invariant property test (23.1)
- `scenarios/config/system_defaults.yaml` - `restraint_memory.allowed_fields`, decay window
- `src/utils/wellness_tracker.py` - cross-session decay (23.2), consolidated remember-view data (23.3)
- `src/app.py` - "What empathySync Remembers" view (23.3)
- `docs/measurement.md` - three-level framework (23.4)
- `MANIFESTO.md`, `CLAUDE.md` - invariant documented

> This phase adds no new data collection. It *constrains* what already exists and proves the constraint holds.

---

## Phase 22: Persistent Agent Daemon 🔜 NEXT (prerequisites 21 and 23.1 complete)

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

**Done when**: `python -m src.daemon.agent` starts, writes a PID file, answers a ping on its local socket, and exits cleanly on SIGTERM; the systemd unit survives `systemctl --user start/stop`; importing anything under `src/daemon/` never imports Streamlit.
**Verify**: new `tests/test_daemon.py` covering start/stop/PID/socket with fakes (no real service install in tests), plus a test asserting `"streamlit" not in sys.modules` after importing the daemon package; full suite passes.
**Pitfalls**: "local socket" means a Unix domain socket, not TCP/HTTP (local-first). If daemon logic needs something currently living in `src/app.py`, move that logic down into `src/models/` or `src/utils/` - never import from the UI layer.

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

**Done when**: schema version is bumped with a `v_n → v_n+1` migration function (MERGE_CHECKLIST storage-change row); every new column is listed in `restraint_memory.allowed_columns`; context injection is built only from structured fields; `tests/test_restraint_memory.py` passes **unmodified**.
**Verify**: a migration test that upgrades a copy of a current-version store; the invariant test; full suite.
**Pitfalls**: no free-text columns of any kind - an LLM-generated summary of what the user said is derived message content and is forbidden by 23.1. If a field feels useful but is not safety-relevant, it does not get stored.

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

**Done when**: nudges fire only through the scheduler with caps enforced; every nudge is logged in allowlisted fields; snooze/dismiss persist across daemon restarts; every nudge body points toward a human or toward exit - never solely back into the app.
**Verify**: scheduler unit tests with an injected clock (test the cap boundary: 2nd nudge in a week fires, 3rd does not; quiet-hours edge minute); full suite.
**Pitfalls**: desktop notification APIs differ per OS - wrap them behind one small interface with a logging no-op fallback so tests never need a display server.

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

**Done when**: the influence score is computed from persisted nudge history only; the four tiers transition at thresholds defined in YAML config (not Python constants); every transition emits a `policy_events` record; the override path exists and the agent states its reason for going quiet.
**Verify**: unit tests driving each tier boundary in both directions (escalate and de-escalate); full suite.
**Pitfalls**: the sign convention matters - nudge engagement correlating with MORE app sessions must push the tier DOWN toward quiet (see Philosophical Safeguards #2). Getting this backwards turns the safety feature into an engagement loop.

### 22.5 Inactivity as Success Metric 🔜 PLANNED
- [ ] Track periods of non-use (especially for sensitive topics)
- [ ] Celebrate milestones: "You haven't needed me for emotional support in 30 days. That's real growth."
- [ ] Distinguish: practical usage staying steady = fine; sensitive usage declining = success
- [ ] Surface in "My Patterns" dashboard when user returns

**Done when**: milestones are computed from timestamps the store already holds (no new tracking fields unless allowlisted); sensitive and practical usage are distinguished; the milestone shows once on the next user-initiated session and never as a push notification.
**Verify**: unit tests with injected clock; full suite.
**Pitfalls**: celebrating absence must not become a re-engagement hook - one showing, then quiet.

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

## Phase 19: Multilingual Support 🔜 PLANNED (after 22)

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

**Files**: `src/models/ai_wellness_guide.py`, `src/models/risk_classifier.py`, `src/models/conversation_session.py` → new YAML under `scenarios/` (follow existing file shapes; see `scenarios/README.md`).
**Done when**: none of the pattern lists named above remain as Python literals in those three files, and behaviour is byte-identical - the full suite passes **without modifying any test expectations**.
**Verify**: `pytest tests/ -m "not conversation"`; `python tests/classification/run_domain_eval.py` (these strings feed classification - must not regress from the 83/94 baseline).
**Pitfalls**: load through the `get_scenario_loader()` singleton (it holds the cache - never instantiate the loader directly); update `scenarios/README.md` per the MERGE_CHECKLIST YAML row; do not rename existing YAML keys or files in the same PR.

### 19.1 Locale Detection 🔜 PLANNED
- [ ] Auto-detect input language via the LLM classifier (add `detected_language` field to `LLMClassification` dataclass)
- [ ] User-settable locale override in `.env` (`LOCALE=fr`, `LOCALE=es`, etc.) and sidebar preference
- [ ] Fall back to `en` if detection is uncertain or LLM is unavailable
- [ ] Language detection runs as part of the existing classification step - no extra Ollama call

**Done when**: `LLMClassification` carries `detected_language`; the value comes from the same single classification call; anything uncertain resolves to `en`; the sidebar override wins over detection.
**Verify**: mocked-httpx tests alongside the existing ones in `tests/test_llm_classifier.py`; `tests/test_data_contracts.py` updated deliberately for the new field; full suite.
**Pitfalls**: the classifier prompt wraps user input in `<user_message>` tags (prompt-injection boundary) - keep that intact when extending the prompt.

### 19.2 Localised YAML Scenarios 🔜 PLANNED
- [ ] Extend `ScenarioLoader` to support locale-scoped loading: `scenarios/domains/crisis.en.yaml`, `crisis.fr.yaml`, etc.
- [ ] Default: if no locale file exists, fall back to `.en.yaml`
- [ ] Priority languages for first translation pass: Spanish (`es`), French (`fr`), Portuguese (`pt`), Arabic (`ar`), Hindi (`hi`)
- [ ] Translation contributors follow `scenarios/TRANSLATING.md` (plain text, no code required)
- [ ] Existing files become `*.en.yaml` - no breaking change to current behaviour
- [ ] Unshelve the completed README translations (7 languages, prepared at `~/shelved/readme-translations/`)

**Done when**: `ScenarioLoader` resolves `<name>.<locale>.yaml` with automatic `.en.yaml` fallback; renaming the existing files changes nothing observable (full suite passes unmodified); `scenarios/TRANSLATING.md` exists.
**Verify**: loader unit tests for locale resolution + fallback; full suite; domain eval unchanged.
**Pitfalls**: the singleton's cache must be keyed by locale or a locale switch mid-process serves stale files; each translated domain file goes through the MERGE_CHECKLIST "new YAML domain file" row (corpus examples included).

### 19.3 Crisis Detection in All Supported Languages 🔜 PLANNED
**Critical requirement**: A missed crisis signal in any language is a safety failure. This sub-phase cannot be skipped.
- [ ] Crisis domain keywords translated and expanded per language (idioms differ - "I can't go on" translates differently than word-for-word)
- [ ] Phase 21 safety model prompted/evaluated in the detected language - the primary cross-language crisis floor
- [ ] Crisis response resources localised: country-specific hotlines, not just English-language ones
- [ ] Test suite: `tests/test_multilingual_crisis.py` - golden crisis phrases in each supported language must always trigger crisis domain
- [ ] Audit: native speaker review required for each language before shipping

**Done when**: every golden crisis phrase in every shipped language routes to the crisis domain with zero misses (this is a 0% false-negative gate, same standard as the English distress corpus); hotline resources exist per country; the native-speaker sign-off is recorded in the PR.
**Verify**: `pytest tests/test_multilingual_crisis.py` plus the full suite; run the conversation-tier crisis scenarios against a multilingual model if available.
**Pitfalls**: do not translate keywords word-for-word - source idioms from native speakers ("I can't go on" has non-literal equivalents). A language without native-speaker review does not ship, even if tests pass.

### 19.4 RTL Layout Support 🔜 PLANNED
- [ ] Detect RTL languages (`ar`, `he`, `fa`, `ur`) from locale setting
- [ ] Inject CSS `direction: rtl` for chat messages in RTL locales
- [ ] Test UI rendering for RTL languages manually

### 19.5 Model Capability Gating 🔜 PLANNED
- [ ] Health check warns if selected model has known weak multilingual support
- [ ] Startup warning if `LOCALE != en` and model is not in recommended multilingual list
- [ ] README documents recommended models per language family

**Done when**: `empathysync --health` (checks live in `src/utils/health_check.py`) shows a `[warn]` when `LOCALE != en` and the configured model is not on the recommended multilingual list; the warning is non-critical (exit code stays 0).
**Verify**: mocked tests alongside the existing health-check tests; full suite.
**Pitfalls**: the recommended-model list belongs in YAML config, not hardcoded in the health check.

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

## Phase 24: Clinician Co-Design Tooling (Guided Form → Reviewed PR) 🔜 PLANNED

Lets non-coding clinicians shape safety-response **language** through a guided
form that opens a reviewed pull request, never a private local edit - so the
public review gate stays intact and no one gets a private safety dial.
Delivers on paper section 5.3 (participatory co-design). See issue #182.

The editable/locked boundary is **decided** (2026-08-11) and enforced now as
`co_design_boundary` in `scenarios/config/system_defaults.yaml` plus a
CODEOWNERS lock on `crisis.yaml`: therapists shape the language (triggers,
response text, response rules); the maintainer keeps the numbers and the floor
(risk weight, thresholds, crisis hard-stop). Still to design: the form itself
(fields, hosting, who may open it), the reviewer UX, the add-vs-remove trigger
guardrail, and - only if it widens past a single trusted reviewer - the
reviewer-pool governance.

**Locked-field snapshot test** (blocks non-crisis `risk_weight` drift) is
deferred until the form exists; until then the only changes come through
maintainer-reviewed PRs.

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

## Current Status (2026-08-01)

**Released**: v1.14.0 (2026-08-01, "Adversarial Restraint Eval"): self
red-teaming Inspect eval, classifier-side domain scorer, `--health` CLI flag,
plus install/test-hermeticity fixes. No pipeline or corpus changes. Prior:
v1.13.0 (2026-07-08, "Safety Guard Integration"). Phases 1-17, 21, and 23.1
complete.

**Safety pipeline depth**: 7 independent layers - post-crisis check, cooldown, keyword
detection, LLM classification, confidence calibration (17.2), distress routing (17.1),
sanity check (17.4). Each layer is independent; failure of one does not bypass others.

**Test suite**: 1150 structural tests + 23 conversation-marked tests (20 quality
scenarios + 3 safety-guard integration). Distress corpus CI gate: 0% FN rate. Keyword
FP rate on benign content: 7%. Domain eval baseline: 83/94 (88%) on mistral:7b-instruct.

**Next**: Phase 22 (daemon), then Phase 19 (multilingual). Phase 23.1 shipped in
v1.12.0; Phase 21 (safety classifier upgrade, issue #125, including the 21.4
domain-routing corrections) shipped in v1.13.0.

**v1.11.0 deferred items - resolved (2026-07-03)**:
- `dev`/`main` branch split: **dropped.** Solo maintainer + branch protection + PR-only
  merges already provide curation; a second long-lived branch doubles the sync surface
  for no benefit at current contributor volume.
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

Shipped versions v0.2 through v1.14.0 are recorded in
[CHANGELOG.md](CHANGELOG.md) and [docs/roadmap-history.md](docs/roadmap-history.md).

**v1.12** (Phase 23.1 + hygiene): negative memory invariant, dead-config removal, pipeline correctness fixes
**v1.13** (Phase 21): purpose-trained safety classifier + domain routing corrections
**v1.14** (tooling): adversarial restraint eval (Inspect) + classifier-side domain scorer + `--health` CLI flag
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
