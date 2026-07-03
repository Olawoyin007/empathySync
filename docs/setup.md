# Setup Guide

This guide walks you through installing and configuring empathySync on your local machine.

## Prerequisites

- **Python 3.10+**
- **Ollama** - Local LLM runtime ([ollama.com](https://ollama.com))
- **Git** (optional, for cloning)

## Step 1: Install Ollama

empathySync runs entirely on your local hardware using Ollama. No data leaves your machine.

### Linux
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

### macOS
```bash
brew install ollama
```

### Windows
Download the installer from [ollama.ai/download](https://ollama.ai/download)

### Start Ollama and pull a model
```bash
# Start the Ollama service
ollama serve

# In another terminal, pull a model (llama2 recommended for balance of speed/quality)
ollama pull llama2

# Or for better responses (requires more RAM):
ollama pull llama3
```

## Step 2: Clone empathySync

```bash
git clone https://github.com/Olawoyin007/empathySync.git
cd empathySync
```

Or download the ZIP from the repository.

## Step 3: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# Linux/macOS:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

## Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 5: Configure Environment

```bash
# Copy the example config
cp .env.example .env

# Edit with your settings
nano .env  # or use any text editor
```

### Required Settings

```env
# Point to your Ollama server
OLLAMA_HOST=http://localhost:11434

# Model you pulled in Step 1
OLLAMA_MODEL=llama2

# Response creativity (0.0-1.0, lower = more focused)
OLLAMA_TEMPERATURE=0.7
```

### Optional Settings

```env
# Application mode
ENVIRONMENT=development
DEBUG=false
LOG_LEVEL=INFO

# Data retention
STORE_CONVERSATIONS=true
CONVERSATION_RETENTION_DAYS=30

# Intelligent classification (Phase 9)
# Uses LLM for context-aware domain detection
LLM_CLASSIFICATION_ENABLED=true
```

## Step 6: Verify Installation

```bash
# Run the test suite
pytest tests/

# Check Ollama connection
curl http://localhost:11434/api/tags
```

## Step 7: Launch empathySync

```bash
streamlit run src/app.py
```

The app opens at `http://localhost:8501`

## Directory Structure After Setup

```
empathySync/
├── .env                  # Your configuration (not in git)
├── data/                 # Your local data (created on first run)
│   ├── wellness_data.json
│   └── trusted_network.json
├── logs/                 # Application logs
└── ...
```

## Common Issues

### "Ollama not responding"

1. Ensure Ollama is running: `ollama serve`
2. Check the host in .env matches your setup
3. Verify a model is pulled: `ollama list`

### "Model not found"

The model name in .env must match exactly what you pulled:
```bash
ollama list  # Shows available models
```

### "Port 8501 already in use"

```bash
# Run on a different port
streamlit run src/app.py --server.port 8502
```

### "Permission denied on data/"

```bash
mkdir -p data logs
chmod 755 data logs
```

## Next Steps

- Read [Usage Guide](usage.md) to learn the interface
- Review [Architecture](architecture.md) to understand the system
- See [CONTRIBUTING.md](../CONTRIBUTING.md) if you want to help develop

---

*All your data stays on your machine. No telemetry, no external calls.*
