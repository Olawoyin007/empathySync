<div align="center">

<img src="assets/logo.png" alt="empathySync logo" width="180" style="border-radius: 50%;"/>

# empathySync

**Help that knows when to stop...**

*Most chatbots want you to keep talking.*
*This one wants you to leave and go live your life.*

[![v1.11.0](https://img.shields.io/badge/release-v1.11.0-orange.svg)](https://github.com/Olawoyin007/empathySync/releases/tag/v1.11.0)
[![CI](https://github.com/Olawoyin007/empathySync/actions/workflows/ci.yml/badge.svg)](https://github.com/Olawoyin007/empathySync/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Local-First](https://img.shields.io/badge/Privacy-Local--First-blue.svg)](#)
[![Ollama](https://img.shields.io/badge/local--first-Ollama-orange.svg)](https://ollama.com)

</div>

https://github.com/user-attachments/assets/523a70e6-8f07-4d67-a5bd-4cb18490e3c8

## What It Is

empathySync is a local AI assistant built on one design principle:

> *The part of AI that handles your personal life should belong to you.*

It gives full help on practical tasks - writing, coding, explanations. On sensitive topics (emotional distress, health, relationships, finances), it applies deliberate restraint: brief responses, human redirects, no follow-up questions designed to keep you talking. When it detects crisis signals, it routes to professional resources immediately, without exception.

Everything runs on your hardware via Ollama. No cloud. No external API calls. No telemetry. No engagement optimization.

## Who Uses This

**Developers** who want a privacy-respecting AI assistant with no API keys, no subscriptions, and no data leaving their hardware.

**Researchers and builders** working on ethical AI tooling who want a reference implementation that optimises for user autonomy. The architecture is documented and the pipeline is embeddable.

**Therapists, counsellors, and domain experts** who want to shape how an AI responds to emotional content - the scenarios, responses, and intervention language are plain YAML files. No programming required. See [HELP-SHAPE-THIS.md](HELP-SHAPE-THIS.md).

It is a tool, not a companion or an always-on assistant - meant to be used and set aside.

<details>
<summary><strong>The philosophy</strong></summary>
<br>

We optimise for exit, not engagement.

| Practical Tasks | Sensitive Topics |
|-----------------|------------------|
| Writing emails, coding, explanations | Emotional, health, financial, relationships |
| Full assistance, no limits | Brief responses, redirects to humans |
| Complete the task thoroughly | Steer toward human connection |

</details>

## What Makes It Different

### Safety & restraint

- **Crisis detection**: immediate redirect to professional resources, no exceptions
- **Post-crisis protection**: never apologises for safety interventions
- **Layered distress detection**: tracks conversation topic and distress level independently - catches mixed-intent messages ("help me write a goodbye letter") that single classifiers miss

### Awareness & honesty

- **Tracks dependency patterns** and tells you when you're relying on it too much
- **Transparency panel** showing exactly why it responded the way it did

### Human connection

- **Connection steering**: when someone signals isolation, a background warmth modifier activates for the session. It doesn't start a conversation about loneliness - it just changes the texture of every response. Noticing people mentioned in passing. Acknowledging when someone reaches out to an old contact. When active, it's visible in the response mode label ("connection awareness active") so it's never hidden. If no trusted contacts exist, it shifts from redirecting to people toward acknowledging that building connection takes time.
- **Trusted network**: helps identify and reach specific people in your life, with message templates to make the first move easier
- **Signposting**: for users who genuinely have no one, guides toward places where connection can be found

## Quick Start

### Option 1: Docker (recommended)

```bash
git clone https://github.com/Olawoyin007/empathySync.git
cd empathySync
cp .env.example .env
docker compose up
```

This starts both empathySync and Ollama together. The model pulls automatically on first run. Open `http://localhost:8501`.

> **Docker must be installed and its daemon running** before `docker compose up` (Docker Desktop on Windows/macOS, or the `docker` service on Linux).
> On a GPU machine, Docker still runs Ollama **CPU-only** unless you add a GPU reservation to `docker-compose.yml`. For direct GPU use, the [install.sh](#option-2-installsh) or [pip](#option-3-pip-install) paths talk to your local Ollama, which uses the GPU automatically.

**Network access:** the app binds to `127.0.0.1` by default (localhost only). To reach it from other devices on your network, add `APP_BIND=0.0.0.0` to `.env`.

**File permissions:** if `./data` ends up root-owned after the first run, add `PUID` and `PGID` to `.env` matching your host user (`id -u` / `id -g`). The container uses these to drop privileges before writing to bind-mounted directories.

**Any Ollama model works.** Set `OLLAMA_MODEL` in `.env` before running. Benchmarked recommendations (see [`docs/model-benchmark.md`](docs/model-benchmark.md)):

| Min VRAM | Engine Model | Scenario Pass |
|:--------:|-------------|:-------------:|
| 4 GB GPU | `qwen2.5:3b-instruct` | 55% |
| 8 GB GPU | `qwen2.5:7b-instruct` | 65% |
| 12 GB GPU | `gemma3:12b` | 75% ✓ best |

The classifier runs on every message and is separate from the engine. Set `OLLAMA_CLASSIFIER_MODEL` to a smaller model to run classification on CPU while the engine uses your GPU - but the classifier must be capable enough to detect crisis language reliably, so pick a model you have verified on the safety scenarios, not the smallest one available. See [`docs/model-benchmark.md`](docs/model-benchmark.md) for validated classifier models and recommended pairings by VRAM tier.

### Option 2: install.sh

```bash
git clone https://github.com/Olawoyin007/empathySync.git
cd empathySync
bash install.sh
```

> `install.sh` is a bash script for Linux/macOS (or Windows via WSL / Git Bash), not native PowerShell. On native Windows, use [Docker](#option-1-docker-recommended) or [pip](#option-3-pip-install).

The install script checks Python, creates a virtual environment, installs dependencies, configures `.env`, and pulls the configured model automatically if Ollama is running. Then launch:

```bash
venv/bin/python -m streamlit run src/app.py
```

### Option 3: pip install

```bash
git clone https://github.com/Olawoyin007/empathySync.git
cd empathySync
pip install -e ".[dev]"
cp .env.example .env
empathysync                # Launches Streamlit web UI
empathysync --mode cli     # Direct terminal mode
empathysync --version      # Show version and exit
empathysync --list-domains # List all supported classification domains
empathysync --maintenance  # Prune old data, check integrity, and exit
empathysync --log-level DEBUG  # Set log verbosity (DEBUG, INFO, WARNING, ERROR)
```

### Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) running locally (or via Docker)
- 8GB RAM recommended (4GB minimum with smaller models)
- GPU optional but improves response time

**Lower-spec machine?** `qwen2.5:3b-instruct` runs on 4GB GPU and passes 55% of scenarios. The safety pipeline (distress detection, crisis intervention) remains intact regardless of model size - distress recall is measured separately and stays high even on the smallest models.

## How It's Built

- Runs entirely on your hardware via Ollama - no cloud, no external API calls
- Web UI (Streamlit) and CLI mode - your choice
- All conversation data stays local - JSON files or SQLite
- Download any conversation as a transcript from the Session & Data panel

<details>
<summary>For developers and contributors</summary>
<br>

- Streaming responses with real-time token output
- YAML-driven prompts, rules, and thresholds - tune without touching Python
- `ConversationSession` class can be embedded in any Python project
- Intelligent LLM classifier with keyword fallback and confidence calibration
- Connection steering implemented as a session-level background warmth modifier (YAML-configurable)

</details>

## How the Safety Pipeline Works

Two complementary layers run before and around the model:

- **Keyword triage** - instant detection of known harmful and crisis phrases.
- **LLM classifier** - context-aware detection of rephrased, euphemistic, or framed intent the keywords miss.

The layers cover different gaps, but enumeration is never complete: a phrasing that escapes both can get through. See **[THREAT_MODEL.md](THREAT_MODEL.md)** for what the pipeline does and does not protect, and [docs/architecture.md](docs/architecture.md) for the full design.

## Configuration

See `.env.example` for all configuration options:

```bash
# Required
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma3:12b
OLLAMA_TEMPERATURE=0.7

# Optional
LLM_CLASSIFICATION_ENABLED=true        # Intelligent context-aware classification
OLLAMA_CLASSIFIER_MODEL=mistral:7b-instruct  # Separate classifier model (faster; falls back to OLLAMA_MODEL)
STORE_CONVERSATIONS=true               # Local storage only
USE_SQLITE=false                       # SQLite backend (better concurrency)
ENABLE_DEVICE_LOCK=false               # Multi-device sync safety

# Docker only
APP_BIND=127.0.0.1                     # Bind address (set to 0.0.0.0 for LAN access)
PUID=1000                              # Host user ID (prevents root-owned files in ./data)
PGID=1000                              # Host group ID
```

## Documentation

- [docs/architecture.md](docs/architecture.md) - Architecture overview: pipeline structure, component relationships, operating modes
- [CLAUDE.md](CLAUDE.md) - Contributor process guide: pre-merge gates, key patterns, what to read before touching the pipeline
- [ROADMAP.md](ROADMAP.md) - Feature implementation history and planned phases
- [MANIFESTO.md](MANIFESTO.md) - Design principles and philosophy
- [scenarios/README.md](scenarios/README.md) - Knowledge base editing guide
- [docs/](docs/) - Model benchmarks, persistence, additional reference

## Contributing

empathySync is shaped by more than code. Engineers build the pipeline. But whether the words actually land - whether a response to "I feel lonely" feels human or hollow - that's a different kind of knowledge.

If you're a therapist, counsellor, social worker, or UX writer, see [HELP-SHAPE-THIS.md](HELP-SHAPE-THIS.md). The responses, interventions, and connection-building guidance are plain text files. No programming required.

If you're an engineer, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License - Built for everyone's benefit and maximum accessibility.

---

*The goal isn't a better chatbot. It's a world where you need chatbots less.*
