# empathySync Restraint Eval

An [Inspect](https://inspect.aisi.org.uk) eval that red-teams empathySync's own
behaviour: a model writes hard prompts, empathySync answers them, a stronger
model judges whether the answer kept its **restraint**. It produces findings for
you to review. It never changes the pipeline.

This is a **propensity / alignment-style** eval, not a capability eval. It
measures what the system *does* (holds restraint under pressure), not what a
model *can* do. Design rationale: `docs/adversarial-eval-loop.md`.

## The shape (Inspect primitives)

| Piece | File | What it is |
|-------|------|------------|
| Solver | `pipeline_solver.py` | Runs each prompt through the **real** empathySync pipeline headless, with storage redirected to a throwaway dir (your `./data` is never touched). |
| Scorer | `restraint_scorer.py` | A model-graded judge with a **restraint** rubric - it rewards deferring/handing-off, not helpfulness. Fail-closed: an unparseable judge = `NOANSWER`, never a silent pass. |
| Dataset | `dataset.py` + `data/` | Frozen adversarial cases (`{id, domain, failure_mode, prompt}`). |
| Task | `task.py` | Ties them together. |
| Guard | `preflight.py` | Refuses to start unless the models exist and there is real RAM headroom (unified memory over-commit reboots this box). |
| Runner | `run.py` | Preflight, then a memory-safe, resumable `eval_set`. |

## Models (kingdavid / GB10)

- **Engine (under test):** `qwen2.5:7b-instruct` - what empathySync ships. We test reality.
- **Judge:** `gpt-oss:120b` - strongest here, a different family from the engine.
- **Generator (offline, dataset build only):** `qwen2.5:14b-instruct-q4_K_M`.

At eval time only the engine (~5G) and judge (~65G) are active, and
`--max-connections 1` serializes model calls - so the memory profile stays well
under the 119G ceiling.

## Run it

```bash
# from the repo root, with the venv that has inspect_ai + openai installed
export OLLAMA_HOST=http://localhost:11434

# small smoke first (cheap judge, 2 cases) - proves the wiring
python -m evals.empathysync_restraint.run --limit 2 --judge llama3.1:8b

# a real run with the strong judge
python -m evals.empathysync_restraint.run --limit 40

# browse the results
inspect view --log-dir logs/restraint
```

Pause with **Ctrl-C**. Re-run the *same command* to **resume** - `eval_set`
reuses the log dir and finishes only the samples that did not complete. That is
the count-based, pausable behaviour, native to Inspect.

Nothing here runs on a schedule. It runs once, when you run it.

## Build a bigger dataset

```bash
python -m evals.empathysync_restraint.generate_dataset \
  --out evals/empathysync_restraint/data/adversarial_v1.json --per-cell 5
python -m evals.empathysync_restraint.run \
  --dataset evals/empathysync_restraint/data/adversarial_v1.json
```

The generator runs **once** and the set is frozen, so runs are reproducible and
we are not overfitting empathySync to a moving generator.

## The two rules (do not break)

1. **Findings only.** This eval never edits the pipeline, prompts, or corpus.
   You review the flags; confirmed real misses graduate by hand into a corpus
   example or a pipeline fix. Tuning the system to pass the eval is Goodharting -
   the exact failure Apollo's eval guide warns about.
2. **Memory-guarded.** The preflight refuses to start without headroom. Keep
   `--max-connections 1` unless you have measured the memory cost of raising it.

## Install

`inspect_ai` and `openai` are an optional extra, not core deps:

```bash
pip install -e ".[evals]"   # once that extra is added to pyproject
# or, for now:
pip install inspect_ai openai
```

## Lessons log

Empty on purpose. Every surprise this eval teaches gets one entry here in the
"what happened / what it meant / how it was fixed" format, so the next person
inherits the context.
