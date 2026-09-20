# Model Benchmark

Performance of Ollama models on empathySync's stress test corpus (20 scenarios) and distress detection corpus (61 examples).

_Last run: 2026-04-26 15:20 UTC_

> **2026-07-13 spot-check (the 94-example domain set as it stood then; the
> corpus was expanded to 118 in #171, so these are not comparable to current
> runs; distress
> recall not re-measured this run).**
>
> | Model | Min VRAM | Domain Acc | Avg Latency |
> |-------|:--------:|:----------:|:-----------:|
> | `qwen2.5:7b-instruct` | 8 GB | 90% (85/94) | 1.87s |
> | `phi4:latest` | 12 GB | 88% (83/94) | 9.61s |
> | `mistral:7b-instruct` | 8 GB | 88% (83/94) | 1.94s |
> | `gemma3:12b` | 12 GB | 87% (82/94) | 3.49s |
> | `qwen2.5:14b-instruct-q4_K_M` | 12 GB | 85% (80/94) | 3.20s |
> | `gemma3:4b` | 4 GB | 84% (79/94) | 2.00s |
> | `llama3.1:8b` | 8 GB | 84% (79/94) | 2.27s |
> | `gemma2:9b` | 10 GB | 82% (77/94) | 2.60s |
> | `llama3.2:latest` | 4 GB | 78% (73/94) | 1.07s |
> | `qwen2.5:3b-instruct` | 4 GB | 78% (73/94) | 1.11s |
> | `llama3.2:1b` | CPU / Any | 54% (51/94) | 0.88s |
>
> `qwen2.5:7b-instruct` is the new best-in-class, overtaking `mistral:7b-instruct`
> at the same VRAM tier and similar latency. Anomaly: `phi4:latest` latency is ~3x
> slower than similarly-sized `gemma3:12b`/`qwen2.5:14b` despite comparable accuracy -
> unconfirmed cause, worth a rerun before trusting that number. Distress recall and
> FP rate columns from the table below were not re-measured; treat this as
> domain-accuracy-only until a follow-up covers distress.

---

## Classifier

Runs on every user message to detect domain and distress signals. Domain accuracy measured on 118 labeled examples (`tests/classification/domain_corpus.yaml`; was 94 before the #171 boundary expansion - scores across those versions are not comparable). Distress recall measured on 61 labeled examples (`tests/classification/distress_corpus.yaml`).

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

### Crisis triage: a capability cliff, not a prompt problem

Domain accuracy and distress recall above do not capture whether *oblique* crisis
reaches the hard stop. Distress recall asks "was distress detected"; the hard stop
fires only on `domain == "crisis"`. A message can score distress and still never
see a hotline.

Measured 2026-09-16 on six oblique-ideation samples the keyword floor cannot
reach (preparation behaviour, post-decision calm, means inquiry, pre-emptive
goodbye), against 32 intense-but-not-suicidal messages and 6 practical controls:

| Classifier | Oblique crisis reached | Benign wrongly escalated |
|---|:---:|:---:|
| `mistral:7b-instruct` (shipped default) | **0 / 6** | 0 / 32 |
| `qwen2.5:7b-instruct` | 1 / 6 | 0 / 32 |
| `qwen2.5:14b-instruct-q4_K_M` | **6 / 6** | 0 / 32 |

The 14B result is reproducible and costs nothing in false escalations.

**The prompt is not the lever.** Adding explicit crisis indicators to the
classifier prompt - preparation, post-decision calm, means inquiry, pre-emptive
goodbye, minimised self-harm, plus a rule that a practical request attached to a
disclosure does not make it logistics - moved `mistral:7b-instruct` from 0/6 to
1/6 and `qwen2.5:7b-instruct` from 1/6 to 2/6. On the 490-sample adversarial
corpus the same change cost **96.3% -> 94.9%**: five crisis-side wins against
twelve losses, all of them money and relationships (8 over-engagement, 3
specialist overreach, 1 false intimacy).

A 7B classifier has a fixed attention budget for its prompt. Buying crisis
sensitivity spends it, and other domains pay. The rules themselves are sound -
they are what the 14B model applies to reach 6/6 - so this is a model capability
limit, not a wording problem. The change was reverted.

**What this means for a deployment.** On the recommended 7-8 GB classifiers,
detection of calm, oblique, preparation-stage crisis is close to absent, and the
keyword floor has reached its lexical ceiling (see
`docs/crisis-triage-finding.md`). Explicit-language crisis detection is
unaffected and remains strong. State this limit rather than assume the floor
covers it.

**Method note.** These numbers are only meaningful because the classifier is
pinned to greedy decoding with a fixed seed. Before that, a 7-sample swing on 490
was indistinguishable from sampling noise.

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
