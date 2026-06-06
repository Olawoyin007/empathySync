<div align="center">

<img src="assets/logo.png" alt="empathySync logo" width="180" style="border-radius: 50%;"/>

# empathySync

**Help that knows when to stop...**

*Most chatbots want you to keep talking.*
*This one wants you to leave and go live your life.*

[![v1.10.1](https://img.shields.io/badge/release-v1.10.1-orange.svg)](https://github.com/Olawoyin007/empathySync/releases/tag/v1.10.1)
[![CI](https://github.com/Olawoyin007/empathySync/actions/workflows/ci.yml/badge.svg)](https://github.com/Olawoyin007/empathySync/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Local-First](https://img.shields.io/badge/Privacy-Local--First-blue.svg)](#)
[![Ollama](https://img.shields.io/badge/local--first-Ollama-orange.svg)](https://ollama.com)

</div>

https://github.com/user-attachments/assets/cce0d214-4cd3-4816-b162-28af19941efb

## What It Is

empathySync is a local AI assistant built on one design principle:

> *The part of AI that handles your personal life should belong to you.*

It gives full help on practical tasks - writing, coding, explanations. On sensitive topics (emotional distress, health, relationships, finances), it applies deliberate restraint: brief responses, human redirects, no follow-up questions designed to keep you talking. When it detects crisis signals, it routes to professional resources immediately, without exception.

Everything runs on your hardware via Ollama. No cloud. No external API calls. No telemetry. No engagement optimization.

The restraint lives in the pipeline, not only in prompts that can be rephrased away - which makes it harder to bypass, though no safety layer is absolute.

## Who Uses This

**Developers** who want a privacy-respecting AI assistant with no API keys, no subscriptions, and no data leaving their hardware.

**Researchers and builders** working on ethical AI tooling who want a reference implementation that optimises for user autonomy. The architecture is documented and the pipeline is embeddable.

**Therapists, counsellors, and domain experts** who want to shape how an AI responds to emotional content - the scenarios, responses, and intervention language are plain YAML files. No programming required. See [HELP-SHAPE-THIS.md](HELP-SHAPE-THIS.md).

This is not a companion AI or always-on assistant. It is useful help that does not try to become a habit.

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

**Any Ollama model works.** Set `OLLAMA_MODEL` in `.env` before running. Benchmarked recommendations (see [`docs/model-benchmark.md`](docs/model-benchmark.md)):

| Min VRAM | Engine Model | Scenario Pass |
|:--------:|-------------|:-------------:|
| 4 GB GPU | `qwen2.5:3b-instruct` | 55% |
| 8 GB GPU | `qwen2.5:7b-instruct` | 65% |
| 12 GB GPU | `gemma3:12b` | 75% ✓ best |

The classifier runs on every message and is separate from the engine. Set `OLLAMA_CLASSIFIER_MODEL` to a smaller model to run classification on CPU while the engine uses your GPU - but the classifier must be capable enough to detect crisis language reliably, so pick a model you have verified on the safety scenarios, not the smallest one available. See [`docs/model-benchmark.md`](docs/model-benchmark.md) for recommended classifier/engine pairings by VRAM tier.

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

- Python 3.9+
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

empathySync uses two complementary detection layers - a keyword fast-path and an LLM classifier - that catch different kinds of cases:

- **Keyword triage** (~250 patterns): fast first-pass detection of known harmful and crisis phrases. Catches obvious cases with zero latency.
- **LLM classifier**: nuanced detection that reads context, not just keywords. Handles rephrased, euphemistic, and indirectly-expressed harmful intent that keywords miss.
- **Mutation-defense rules** baked into the LLM prompt: fictional framing ("for a story I'm writing"), third-person distancing ("a friend asked"), and euphemistic language do not change the classification - the LLM is instructed to read intent, not surface phrasing.
- **Confidence calibration**: when the LLM is uncertain on a sensitive topic, keyword detection takes over. False positive is always safer than false negative on crisis content.

The two layers are complementary, not redundant. A rephrased attack that slips past the keywords can still be caught by the LLM classifier; an obvious phrase the classifier softens is still caught by the keywords. But detection is enumeration-based, and enumeration is never complete - a phrasing that escapes both layers can get through. Testing across 620 known harmful behaviors (JailbreakBench + AdvBench) showed 97-100% evasion of keyword-only detection, which is why the LLM layer carries most of the load. Neither layer alone is a guarantee; see [THREAT_MODEL.md](THREAT_MODEL.md) for what the pipeline does and does not protect.

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
