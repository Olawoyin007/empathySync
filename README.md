<div align="center">

<img src="assets/logo.png" alt="empathySync logo" width="180" style="border-radius: 50%;"/>

# empathySync

**Help that knows when to stop...**

*Most chatbots want you to keep talking.*
*This one wants you to leave and go live your life.*

[![v1.4](https://img.shields.io/badge/release-v1.4-orange.svg)](https://github.com/Olawoyin007/empathySync/releases/tag/v1.4)
[![CI](https://github.com/Olawoyin007/empathySync/actions/workflows/ci.yml/badge.svg)](https://github.com/Olawoyin007/empathySync/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Local-First](https://img.shields.io/badge/Privacy-Local--First-blue.svg)](#)
[![Ollama](https://img.shields.io/badge/local--first-Ollama-orange.svg)](https://ollama.com)

</div>

<!-- Screenshot: place image in assets/ and uncomment the line below once available -->
<!-- ![empathySync interface showing the transparency panel](assets/screenshot.png) -->

## What It Is

Every AI assistant is built to keep you talking. empathySync is the only one built to make itself less needed.

Full help for practical tasks. Deliberate restraint on personal ones. When it detects you're spiralling, it redirects you to real humans - not more conversation. Everything runs on your hardware via Ollama. No cloud. No data harvesting. No engagement optimization.

Your inner life deserves something that knows the difference.

<details>
<summary><strong>The belief behind it</strong></summary>
<br>

Every person should have the right to an AI system that is entirely their own. Not rented. Not monitored. Not optimised for someone else's engagement metrics. Yours - running on your hardware, answering only to you, storing nothing it doesn't need to.

For sensitive, personal things - how you're feeling, your relationships, your health, your money - you deserve something local, private, and restrained. For complex tasks that need serious compute, use the cloud AIs. That's a reasonable division.

But the part of AI that touches your inner life should belong to you.

This isn't a feature. It's the point.

</details>

## Who Is This For?

If you're a **developer** who wants a privacy-respecting AI assistant with no API keys, no subscriptions, and no data leaving your hardware - this is for you.

If you're building **ethical AI tooling** and want a reference implementation that optimises for user autonomy rather than engagement, the architecture is fully documented and embeddable.

If you're a **therapist, counsellor, or domain expert** who wants to shape how an AI responds to emotional content - see [HELP-SHAPE-THIS.md](HELP-SHAPE-THIS.md).

empathySync is **not** for people who want a companion AI or always-on assistant. It's for people who want useful help that doesn't try to become a habit.

<details>
<summary><strong>The philosophy</strong></summary>
<br>

We optimise for exit, not engagement.

| Practical Tasks | Sensitive Topics |
|-----------------|------------------|
| Writing emails, coding, explanations | Emotional, health, financial, relationships |
| Full assistance, no limits | Brief responses, redirects to humans |
| Complete the task thoroughly | Encourage human connection |

</details>

## What Makes It Different

### Safety & restraint

- **Crisis detection**: immediate redirect to professional resources, no exceptions
- **Post-crisis protection**: never apologises for safety interventions

### Awareness & honesty

- **Tracks dependency patterns** and warns you if you're relying on it too much
- **Transparency panel** showing exactly why it responded the way it did
- **Anti-engagement metrics**: fewer sensitive sessions = success

### Human connection

- **Suggests real humans** to talk to, and helps you find them if you don't have anyone yet

## Quick Start

### Option 1: Docker (recommended)

```bash
git clone https://github.com/Olawoyin007/empathySync.git
cd empathySync
cp .env.example .env
docker compose up
```

This starts both empathySync and Ollama together. The model pulls automatically on first run. Open `http://localhost:8501`.

**Any Ollama model works** - `qwen2.5:7b-instruct`, `llama3.1:8b`, `mistral:7b`, whatever you already have. Set `OLLAMA_MODEL` in `.env` before running. Recommended: `qwen2.5:7b-instruct` for best quality.

### Option 2: install.sh

```bash
git clone https://github.com/Olawoyin007/empathySync.git
cd empathySync
bash install.sh
```

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
empathysync          # Launches Streamlit web UI
empathysync --mode cli  # Direct terminal mode
```

### Requirements

- Python 3.9+
- [Ollama](https://ollama.com/) running locally (or via Docker)
- 8GB RAM recommended (4GB minimum with smaller models)
- GPU optional but improves response time

**Lower-spec machine?** Smaller models like `qwen2.5:3b` or `tinyllama` run comfortably on 4GB RAM. The safety pipeline remains intact regardless of model size.

## Technical Foundation

- **Local LLM**: Runs entirely on your hardware via Ollama
- **Privacy-First**: Zero external API calls, complete data sovereignty
- **Dual Interface**: Streamlit web UI or direct CLI mode (`empathysync --mode cli`)
- **Streaming Responses**: Real-time token streaming for faster perceived response times
- **YAML-Driven**: All prompts, rules, and thresholds configurable
- **LLM Classification**: Optional intelligent classification for nuanced context detection
- **Framework-Agnostic Core**: `ConversationSession` class can be embedded in any Python project

## Configuration

See `.env.example` for all configuration options:

```bash
# Required
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
OLLAMA_TEMPERATURE=0.7

# Optional
LLM_CLASSIFICATION_ENABLED=true  # Intelligent context-aware classification
STORE_CONVERSATIONS=true         # Local storage only
USE_SQLITE=false                 # SQLite backend (better concurrency)
ENABLE_DEVICE_LOCK=false         # Multi-device sync safety
```

## Documentation

- [CLAUDE.md](CLAUDE.md) - Architecture and development guide
- [ROADMAP.md](ROADMAP.md) - Detailed feature implementation plan
- [MANIFESTO.md](MANIFESTO.md) - Design principles and philosophy
- [scenarios/README.md](scenarios/README.md) - Knowledge base editing guide
- [docs/](docs/) - Additional documentation

## Contributing

empathySync is shaped by more than code. Engineers build the pipeline. But whether the words actually land - whether a response to "I feel lonely" feels human or hollow - that's a different kind of knowledge.

If you're a therapist, counsellor, social worker, or UX writer, see [HELP-SHAPE-THIS.md](HELP-SHAPE-THIS.md). The responses, interventions, and connection-building guidance are plain text files. No programming required.

If you're an engineer, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License - Built for everyone's benefit and maximum accessibility.

---

*The goal isn't a better chatbot. It's a world where you need chatbots less.*
