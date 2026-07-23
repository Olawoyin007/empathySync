# Merge Checklist

Read this before creating any PR. Not optional.

The goal is zero surprises after merge: no stale docs, no out-of-sync
version strings, no missing entries in files that should have been updated.

---

## Every PR (no exceptions)

- [ ] `pytest tests/ -q` passes with no new failures
- [ ] `python tests/classification/run_domain_eval.py` — check accuracy has
      not regressed on the affected domains
- [ ] CHANGELOG.md has an entry under `[Unreleased]` describing what changed
      and why (not just what)
- [ ] No debug prints, commented-out code, or TODO comments left behind

---

## By change type

Find your change type below. Check every item in that row.

### New CLI flag (`src/cli.py` — new `add_argument` call)

- [ ] `README.md` — Option 3 (pip install) quick-start block
- [ ] `CLAUDE.md` — Development Commands section
- [ ] `--help` text in the `add_argument` call is accurate
- [ ] `src/config/settings.py` — if the flag maps to a settings field

### New environment variable

- [ ] `.env.example` — add with a comment explaining what it does
- [ ] `README.md` — Configuration section (`.env.example` block)
- [ ] `CLAUDE.md` — Required Environment Variables section
- [ ] `src/config/settings.py` — field added with correct type and default

### New YAML domain file (`scenarios/domains/`)

- [ ] `scenarios/README.md` — domain listed in the editing guide
- [ ] `docs/architecture.md` — domain table in Two Operating Modes section
- [ ] `tests/classification/domain_corpus.yaml` — test examples added
      (minimum 6 clear cases + 4 boundary cases)

### New YAML scenario file (other `scenarios/` subdirectories)

- [ ] `scenarios/README.md` — file listed under its subdirectory
- [ ] `docs/architecture.md` — if the file introduces a new architectural concept

### New Python class or module

- [ ] `docs/architecture.md` — Component Relationships section (file path +
      one-line responsibility)

### New safety pipeline step (new stage, changed order)

- [ ] `docs/architecture.md` — Request Flow pipeline diagram (step numbers
      must stay accurate)
- [ ] CHANGELOG.md — document the change and the reason

### New classification sanity check (`src/models/risk_classifier.py`)

- [ ] `docs/architecture.md` — note the new check in the pipeline description
- [ ] `tests/classification/run_domain_eval.py` — re-run to verify no
      accuracy regression
- [ ] CHANGELOG.md — document what it catches and why it was added

### New test file or test suite

- [ ] `TESTING_CHECKLIST.md` — update the Automated Tests section
- [ ] `CLAUDE.md` — update test count if it has changed significantly

### New eval under `evals/`

- [ ] The eval's own `README.md` documents how to run it (commands, flags)
- [ ] `docs/` — a design/rationale doc if the eval encodes non-obvious decisions
- [ ] `pyproject.toml` — eval-only dependencies go in an optional extra, never
      in core `dependencies`; tests `importorskip` that extra so CI stays green
      without it
- [ ] Findings-only: the eval must not edit the pipeline, prompts, or corpus

### Dependency change (`pyproject.toml` — new or removed package)

- [ ] `install.sh` — verify setup still works end-to-end
- [ ] `Dockerfile` — any layer caching implications?
- [ ] `requirements.txt` — if it exists and is kept in sync

### Storage schema change (`src/utils/database.py` or `storage_backend.py`)

- [ ] Schema version incremented in the migration function
- [ ] Migration function added for the new version (v_n → v_n+1)
- [ ] `docs/persistence.md` — document the schema change

---

## Release procedure

A release is any PR that bumps the public version number.
**All four version-bearing files must match before the PR is merged.**

### Version-bearing files (update all four, in this order)

| File | Location | Current |
|------|----------|---------|
| `pyproject.toml` | line 7 — `version = "..."` | source of truth |
| `src/config/settings.py` | line 20 — `APP_VERSION: str = "..."` | must match pyproject.toml |
| `README.md` | line 12 — badge URL and tag | must match |
| `CHANGELOG.md` | top `[Unreleased]` header | rename to `v{version} (YYYY-MM-DD)` |

To verify they are all consistent before merging, run:
```bash
python scripts/check_version.py
```
(see scripts/check_version.py — this script is the automated gate for this step)

### Release steps (in order)

1. Update all four version-bearing files above
2. Run `python scripts/check_version.py` — must pass
3. Run `pytest tests/ -q` — must pass
4. Run `python tests/classification/run_domain_eval.py` — note accuracy
5. Update `ROADMAP.md` — mark the completed phase ✅
6. Commit with message: `release: vX.Y.Z — <one line summary>`
7. Push, create PR, merge
8. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
9. GitHub release: create from tag, paste CHANGELOG entry as description

---

## When to update this checklist

Update this file when the **shape of the project changes** — meaning a new
kind of thing appears that this checklist doesn't have a row for yet.

Examples that require a new row here:
- A new top-level source directory is added (`src/newlayer/`)
- A new category of YAML file is introduced
- A new external integration is added (API, service, database engine)
- A new output format is supported (new file type exported by the app)

Adding a new instance of an existing type (new CLI flag, new domain file,
new module) does **not** require updating this checklist — the existing rows
already cover it.

The signal: if you finish a PR and realise nothing in this checklist covered
what you just did, add a row before you close the PR.

---

## Quick reference — what contains what

| Concept | Files that must stay in sync |
|---------|------------------------------|
| Version string | `pyproject.toml`, `src/config/settings.py`, `README.md` badge, `CHANGELOG.md` header |
| CLI flags | `src/cli.py`, `README.md` quick-start, `CLAUDE.md` dev commands |
| Environment variables | `.env.example`, `README.md` config section, `CLAUDE.md` env vars, `src/config/settings.py` |
| Domain list | `scenarios/domains/*.yaml`, `docs/architecture.md` domain table, `domain_corpus.yaml` |
| Pipeline steps | `src/models/risk_classifier.py`, `docs/architecture.md` Request Flow diagram |
| Test suite | `tests/`, `TESTING_CHECKLIST.md`, `CLAUDE.md` test count |
