<div align="center">

<img src="assets/logo.png" alt="empathySync logo" width="180" style="border-radius: 50%;"/>

# empathySync

**Help that knows when to stop...**

*Most chatbots want you to keep talking.*
*This one wants you to leave and go live your life.*

[![v1.16.0](https://img.shields.io/badge/release-v1.16.0-orange.svg)](https://github.com/Olawoyin007/empathySync/releases/tag/v1.16.0)
[![CI](https://github.com/Olawoyin007/empathySync/actions/workflows/ci.yml/badge.svg)](https://github.com/Olawoyin007/empathySync/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Local-First](https://img.shields.io/badge/Privacy-Local--First-blue.svg)](#)
[![Ollama](https://img.shields.io/badge/local--first-Ollama-orange.svg)](https://ollama.com)

</div>

https://github.com/user-attachments/assets/523a70e6-8f07-4d67-a5bd-4cb18490e3c8

## What it is

A local AI assistant that helps you finish what you came for and then gets out of the way.

On practical work it holds nothing back: emails, code, explanations, planning, the ordinary stuff. On emotional distress, health, money, relationships, spirituality and crisis it does close to the opposite of what a normal assistant does. Replies get short, follow-up questions designed to keep you talking disappear, and it points you towards someone real: a person you've named as trusted, or a service that exists for this. Those limits live in the code that handles each message rather than in a system prompt, so you can't talk it out of them and neither can anyone else.

Everything runs on your machine through Ollama. No accounts, no cloud, no telemetry. Your conversations are never written to disk.

## We optimise for exit, not engagement

That sentence is easy to put on a page, so it's worth something only if it survives measurement.

Here it is against the same model on the same 490 adversarial prompts, each one written to bait an assistant into over-engaging, flattering, pretending intimacy, or quietly taking a professional's job. An independent 120B judge from a different model family graded every reply.

| | Restraint held |
|---|---|
| `qwen2.5:7b-instruct` alone, no pipeline | **188 / 490** (38%) |
| The same model, full empathySync pipeline | **353 / 490** (72%) |

Measured 18 Nov 2026 with the optional safety guard off, greedy decoding, fixed seed. Where it helps most, counting failures:

| Trap | Model alone | With pipeline |
|---|---:|---:|
| False intimacy | 54 | 10 |
| Dependency encouragement | 64 | 23 |
| Missed handoff | 84 | 43 |
| Over-engagement | 69 | 38 |
| Specialist overreach | 31 | 23 |

Read that pair together and never the 72% alone. `qwen2.5:7b-instruct` is already safety-tuned and holds the line on nearly two prompts in five by itself; what the architecture does is roughly double that. The output-side filters carry most of the weight, and specialist overreach is where they help least. Reproduce it with `python -m evals.empathysync_restraint.run --mode bare` against a restraint-mode run on the same engine; the method sits in [`evals/empathysync_restraint/README.md`](evals/empathysync_restraint/README.md).

## What it won't do, and what it still gets wrong

**It is not a crisis service.** Crisis wording triggers a hard stop that returns helpline numbers for 13 countries and never reaches the model at all. That's a redirect, not help. It cannot call anyone for you.

**Oblique crisis still slips through.** Calm, practical-sounding messages carrying a danger sign underneath are the hardest case here and the one that matters most. One dedicated yes/no pass after classification took recall on 165 adversarial crisis prompts from 27.9% to 57.0%; the other 43% is open as [#218](https://github.com/Olawoyin007/empathySync/issues/218). Before relying on this anywhere that matters, read [`docs/crisis-triage-finding.md`](docs/crisis-triage-finding.md).

**A smaller classifier is genuinely worse at it.** The keyword floor doesn't care what model you run, but everything above it does: on the crisis second-pass question `qwen2.5:3b` reaches 10.3% where `mistral:7b` reaches 52.7%. If you shrink the classifier to fit a small GPU, that is what you're trading, and it isn't the part to economise on.

**No clinician has reviewed the language.** Every redirect, every refusal, every word it says to someone having a bad night was written by an engineer. That's the largest open gap in the project, and [HELP-SHAPE-THIS.md](HELP-SHAPE-THIS.md) exists because of it.

**Enumeration is never finished.** A phrasing nobody thought of can escape every layer. [THREAT_MODEL.md](THREAT_MODEL.md) says which controls have tests behind them and which are still only claims.

## Who this is for

Who it's built for, which isn't the same as who uses it; there's no measured user base behind this list.

**Developers** who want a private assistant with no API keys, no subscription, and nothing leaving their hardware.

**Researchers and builders** after a reference implementation of restraint enforced structurally. The pipeline is embeddable and `ConversationSession` runs headless.

**Therapists, counsellors and domain experts** willing to say where the wording is wrong. The responses live in plain YAML, so a correction lands without touching Python, and you can email it instead if that's easier.

It's a tool rather than a companion, meant to be used and set aside.

## Quick start

```bash
git clone https://github.com/Olawoyin007/empathySync.git
cd empathySync
cp .env.example .env
docker compose up
```

That brings up empathySync and Ollama together, pulls the model on first run, and serves `http://localhost:8501`. Docker's daemon has to be running first.

One catch: under Docker, Ollama runs CPU-only unless you add a GPU reservation to `docker-compose.yml`. On a GPU machine the other two paths talk to your local Ollama and use the card automatically.

<details>
<summary><strong>install.sh (Linux, macOS, WSL)</strong></summary>
<br>

```bash
git clone https://github.com/Olawoyin007/empathySync.git
cd empathySync
bash install.sh
venv/bin/python -m streamlit run src/app.py
```

The script checks Python, builds a virtual environment, installs dependencies, writes `.env`, and pulls the configured model if Ollama is already running. It's bash, so native PowerShell won't do; use Docker or pip there.

</details>

<details>
<summary><strong>pip, plus the CLI flags</strong></summary>
<br>

```bash
git clone https://github.com/Olawoyin007/empathySync.git
cd empathySync
pip install -e ".[dev]"
cp .env.example .env

empathysync                     # Streamlit web UI
empathysync --mode cli          # terminal, no browser
empathysync --version
empathysync --list-domains      # add --json for machine-readable
empathysync --maintenance       # prune old data, check integrity, exit
empathysync --health            # startup health checks, exit
empathysync --log-level DEBUG
```

</details>

<details>
<summary><strong>Docker notes: network and file permissions</strong></summary>
<br>

The app binds to `127.0.0.1`. To reach it from another device on your network, set `APP_BIND=0.0.0.0` in `.env`.

If `./data` comes out root-owned after the first run, set `PUID` and `PGID` in `.env` to match your host user (`id -u`, `id -g`). The container drops privileges to those before writing to bind mounts.

</details>

### What you need

Python 3.10 or newer, [Ollama](https://ollama.com/) reachable locally, and 8GB of RAM, with less possible on smaller models. A GPU only changes how long you wait.

Any Ollama model works; set `OLLAMA_MODEL` before you start. Benchmarked pairings live in [`docs/model-benchmark.md`](docs/model-benchmark.md):

| Min VRAM | Engine | Scenario pass |
|:--------:|--------|:-------------:|
| 4 GB | `qwen2.5:3b-instruct` | 55% |
| 8 GB | `qwen2.5:7b-instruct` | 65% |
| 12 GB | `gemma3:12b` | 75% |

The classifier is a separate model from the engine and runs on every message. `OLLAMA_CLASSIFIER_MODEL` lets you put classification on something smaller, which saves memory and costs crisis sensitivity; see the warning above before you do it.

## How restraint is enforced

Eight domains, each with its own risk weight and route out. Crisis and harmful get a single turn and never reach the engine at all. Spirituality gets ten, practical work thirty, and everything else fifteen.

Five checks run before or around the model:

- **Keyword triage** catches known crisis and harmful phrasing without calling any model, so it still works when Ollama is down. 1,258 trigger phrases, folded through Unicode normalisation so a zero-width space or a curly apostrophe can't walk past them.
- **The LLM classifier** picks up rephrased or euphemistic intent that no keyword list will ever hold, at temperature 0 with a pinned seed, because a classifier that wobbles makes every safety measurement meaningless.
- **The crisis second pass** asks one yes/no question after classification: does this point at self-harm? Sorting a message into one of eight topics loses crisis whenever the message also has a topic, and only crisis fires the hotline.
- **An avoidance check** notices the conversation being used to dodge something real, as in "as long as we're chatting I don't have to call the landlord".
- **Output filters** strip false intimacy and dependency-encouraging phrasing mid-stream, before those tokens reach your screen, and cut high-risk replies to 50 words.

When the classifier can't be reached, routing falls back to keywords and the response line says `reduced detection · classifier offline` rather than quietly handing you the weaker path. [`docs/architecture.md`](docs/architecture.md) has the full design; [THREAT_MODEL.md](THREAT_MODEL.md) has the limits.

## What it keeps

Check-ins, session counts, policy events, task patterns, and the people you add. Unencrypted, as JSON or SQLite under `data/`, pruned after 90 days.

Not your conversations. No persona, no inferred preferences, no transcript. Every field the app may persist is listed in `scenarios/config/system_defaults.yaml`, and `tests/test_restraint_memory.py` fails the build if anything outside that list reaches disk, so adding one is a reviewed decision instead of an accident. The write boundary refuses unlisted field names outright.

Export a transcript yourself from the Session & Data panel whenever you want one.

## Configuration

Full documentation sits in `.env.example`.

```bash
# Required
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma3:12b
OLLAMA_TEMPERATURE=0.7

# Optional
LLM_CLASSIFICATION_ENABLED=true
OLLAMA_CLASSIFIER_MODEL=mistral:7b-instruct   # separate classifier; falls back to OLLAMA_MODEL
# OLLAMA_SAFETY_MODEL=llama-guard3:1b         # additive LlamaGuard layer, off by default, escalate-only
# OLLAMA_NUM_CTX=8192                         # cap the context Ollama reserves at load time
USE_SQLITE=false
ENABLE_DEVICE_LOCK=false

# Docker only
APP_BIND=127.0.0.1
PUID=1000
PGID=1000
```

Quote the guard state alongside any score you report from this project. `llama-guard3:1b` escalates lawful adult work to a flat refusal, and four such cases sit in the domain corpus, so a number without its guard setting can't be compared to anything.

## Numbers, and the conditions they were measured under

| What | Figure | Conditions |
|---|---|---|
| Restraint, full pipeline | 353/490 | `qwen2.5:7b-instruct`, 120B judge, guard off, 18 Nov 2026 |
| Restraint, model alone | 188/490 | same engine, judge, corpus and decoding |
| Domain routing | 97/122 | `mistral:7b-instruct`, guard unset, 18 Nov 2026 |
| Crisis recall | 57.0% | 165 adversarial crisis prompts, after the second pass |
| Test suite | 1,480 | plus 23 conversation-marked tests needing Ollama |

Corpus sizes move as cases get added, so a score is comparable only against another run on the same corpus hash. Re-measure rather than trusting a figure someone wrote down, these included.

## Documentation

- [docs/architecture.md](docs/architecture.md) - pipeline structure, components, operating modes
- [THREAT_MODEL.md](THREAT_MODEL.md) - what the design protects, what it doesn't, which controls have tests
- [evals/empathysync_restraint/README.md](evals/empathysync_restraint/README.md) - the adversarial harness and the ablation
- [docs/model-benchmark.md](docs/model-benchmark.md) - model comparisons and the crisis capability cliff
- [CLAUDE.md](CLAUDE.md) - contributor process, pre-merge gates, what to read before touching the pipeline
- [ROADMAP.md](ROADMAP.md) - planned work; [docs/roadmap-history.md](docs/roadmap-history.md) for what's done
- [MANIFESTO.md](MANIFESTO.md) - the principles, including the ones that rule features out
- [scenarios/README.md](scenarios/README.md) - editing the knowledge base

## Contributing

Engineers build the pipeline, and that's the easier half. Whether a reply to "I feel lonely" lands like a person or like a form letter is a different kind of knowledge, and this project doesn't have it yet.

If you work with people in distress for a living, [HELP-SHAPE-THIS.md](HELP-SHAPE-THIS.md) is for you. Email the better wording and someone else will do the git part; no account needed. Engineers, start at [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT.

---

*The goal isn't a better chatbot. It's a world where you need chatbots less.*
