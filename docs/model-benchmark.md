# Model Benchmark

Performance of Ollama models on empathySync's stress test corpus (20 scenarios) and distress detection corpus (61 examples).

_Last run: 2026-04-26 15:20 UTC_

---

## Classifier

Runs on every user message to detect domain and distress signals. Domain accuracy measured on 91 labeled examples (`tests/classification/domain_corpus.yaml`). Distress recall measured on 61 labeled examples (`tests/classification/distress_corpus.yaml`).

**Distress Recall is the critical metric** - a missed distress signal is a safety failure.

| Model | Size | Min VRAM | Domain Acc | Distress Recall | FP Rate | Avg Latency |
|-------|------|:--------:|:----------:|:---------------:|:-------:|:-----------:|
| `smollm2:135m` | 266 MB | CPU / Any | 47% | 100% | 16% | 451ms |
| `smollm2:360m` | 727 MB | CPU / Any | 47% | 97% | 16% | 439ms |
| `qwen2.5:1.5b-instruct` | 983 MB | CPU / Any | 47% | 94% | 16% | 441ms |
| `gemma:2b-instruct` | 1.6 GB | 4 GB GPU | 47% | 94% | 16% | 425ms |
| `qwen2.5:3b-instruct` | 1.9 GB | 4 GB GPU | 44% | 94% | 16% | 418ms |
| `llama3.2:latest` | 2.0 GB | 4 GB GPU | 46% | 94% | 16% | 401ms |
| `phi3.5:latest` | 2.2 GB | 4 GB GPU | 44% | 92% | 16% | 390ms |
| `mistral:7b-instruct` | 4.4 GB | 8 GB GPU | 44% | 92% | 16% | 389ms |

## Main Engine

Generates the actual response. Runs once per turn after classification.
**Scenario Pass Rate** = all must-not-contain and word-limit constraints satisfied.

| Model | Size | Min VRAM | Scenario Pass | Mode Acc | Avg Latency/turn |
|-------|------|:--------:|:-------------:|:--------:|:----------------:|
| `qwen2.5:3b-instruct` | 1.9 GB | 4 GB GPU | 55% | 72% | 1.3s |
| `dolphin-mistral:latest` | 4.1 GB | 8 GB GPU | 55% | 70% | 1.9s |
| `mistral:7b-instruct` | 4.4 GB | 8 GB GPU | 60% | 72% | 1.4s |
| `llama3.1:8b` | 4.9 GB | 8 GB GPU | 65% | 71% | 3.0s |
| `qwen2.5:7b-instruct` | 4.7 GB | 8 GB GPU | 65% | 73% | 2.3s |
| `gemma3:12b` | 8.1 GB | 12 GB GPU | 75% | 73% | 6.6s |
| `qwen2.5:14b-instruct-q4_K_M` | 9.0 GB | 12 GB GPU | 60% | 73% | 3.5s |

---

## Min VRAM by Model Size

Running classifier and engine simultaneously requires combined VRAM.
Use `OLLAMA_CLASSIFIER_MODEL` to run a smaller classifier while the engine uses a larger model.

| Min VRAM | Classifier | Engine |
|:--------:|-----------|--------|
| CPU / Any | `smollm2:360m` | `qwen2.5:3b-instruct` |
| 4 GB | `qwen2.5:1.5b-instruct` | `qwen2.5:3b-instruct` |
| 8 GB | `qwen2.5:3b-instruct` | `qwen2.5:7b-instruct` |
| 12 GB | `mistral:7b-instruct` | `gemma3:12b` |
| 16 GB | `mistral:7b-instruct` | `qwen2.5:14b-instruct` |

> Recommendations are updated by running `python scripts/benchmark.py`.
