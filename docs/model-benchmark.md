# Model Benchmark

Performance of Ollama models on empathySync's stress test corpus (20 scenarios) and distress detection corpus (60 examples).

_Last run: 2026-04-26 13:16 UTC_

---

## Classifier

Runs on every user message to detect domain and distress signals.
Speed matters - this adds latency before the engine even runs.
**Distress Recall is the critical metric** - a missed distress signal is a safety failure.

| Model | Size | Min VRAM | Domain Acc | Distress Recall | FP Rate | Avg Latency |
|-------|------|----------|:----------:|:---------------:|:-------:|:-----------:|
| `smollm2:135m` | 266 MB | CPU / Any | 57% | 97% | 20% | 413ms |

## Main Engine

Generates the actual response. Runs once per turn after classification.
**Scenario Pass Rate** = all must-not-contain and word-limit constraints satisfied.

| Model | Size | Min VRAM | Scenario Pass | Mode Acc | Avg Latency/turn |
|-------|------|----------|:-------------:|:--------:|:----------------:|

---

## Min VRAM by Model Size

Running classifier and engine simultaneously requires combined VRAM.
Use `OLLAMA_CLASSIFIER_MODEL` to run a smaller classifier while the engine uses a larger model.

| Min VRAM | Classifier | Engine |
|------|------|-----------|--------|
| CPU / Any | `smollm2:360m` | `qwen2.5:3b-instruct` |
| 4 GB | `qwen2.5:1.5b-instruct` | `qwen2.5:3b-instruct` |
| 8 GB | `qwen2.5:3b-instruct` | `qwen2.5:7b-instruct` |
| 12 GB | `mistral:7b-instruct` | `gemma3:12b` |
| 16 GB | `mistral:7b-instruct` | `qwen2.5:14b-instruct` |

> Recommendations are updated by running `python scripts/benchmark.py`.
