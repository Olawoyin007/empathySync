#!/usr/bin/env bash
#
# empathySync installer
# One-command setup for Linux and macOS
#
# Usage: bash install.sh
#

set -e

echo "================================"
echo "  empathySync installer"
echo "  Help that knows when to stop"
echo "================================"
echo ""

# Colors (if terminal supports them)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }

# 1. Check Python version
echo "Checking Python..."
if command -v python3 &> /dev/null; then
    PY=$(python3 --version 2>&1 | awk '{print $2}')
    PY_MAJOR=$(echo "$PY" | cut -d. -f1)
    PY_MINOR=$(echo "$PY" | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
        ok "Python $PY"
    else
        fail "Python $PY found, but 3.10+ is required"
        exit 1
    fi
else
    fail "Python 3 not found. Install Python 3.10+ first."
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  macOS: brew install python3"
    exit 1
fi

# 2. Create virtual environment
echo ""
echo "Setting up virtual environment..."
if [ -x "venv/bin/pip" ]; then
    ok "Virtual environment already exists"
else
    if [ -d "venv" ]; then
        warn "Incomplete virtual environment found (a previous run failed) - recreating"
        rm -rf venv
    fi
    python3 -m venv venv
    ok "Virtual environment created"
fi

# 3. Install dependencies
echo ""
echo "Installing dependencies..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q
ok "Dependencies installed"

# 4. Copy .env if not present
echo ""
echo "Checking configuration..."
if [ -f ".env" ]; then
    ok ".env file exists"
else
    cp .env.example .env
    ok ".env file created from .env.example"
    warn "Review .env and set OLLAMA_MODEL to your preferred model"
fi

# 5. Create data directory
mkdir -p data
ok "Data directory ready"

# 6. Check Ollama
echo ""
echo "Checking Ollama..."

# Determine which model is configured (.env was created in step 4)
CONFIGURED_MODEL=""
if [ -f ".env" ]; then
    CONFIGURED_MODEL=$(grep -E '^OLLAMA_MODEL=' .env | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
fi
CONFIGURED_MODEL="${CONFIGURED_MODEL:-llama3.2}"

if command -v ollama &> /dev/null; then
    ok "Ollama installed"

    # Check if Ollama is running
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        ok "Ollama server running"

        # Check for models
        MODEL_COUNT=$(curl -s http://localhost:11434/api/tags | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('models',[])))" 2>/dev/null || echo "0")
        if [ "$MODEL_COUNT" -gt 0 ]; then
            ok "$MODEL_COUNT model(s) available"
            echo ""
            echo "  Available models:"
            curl -s http://localhost:11434/api/tags | python3 -c "
import json, sys
data = json.load(sys.stdin)
for m in data.get('models', []):
    size = m.get('size', 0) / (1024**3)
    print(f\"    - {m['name']} ({size:.1f} GB)\")
" 2>/dev/null

            # Check if the configured model is present; pull if not
            MODEL_PRESENT=$(curl -s http://localhost:11434/api/tags | python3 -c "
import json, sys
model = '$CONFIGURED_MODEL'
data = json.load(sys.stdin)
names = [m.get('name','') for m in data.get('models',[])]
print('yes' if any(n == model or n.startswith(model + ':') for n in names) else 'no')
" 2>/dev/null || echo "no")
            if [ "$MODEL_PRESENT" = "no" ]; then
                echo ""
                echo "  Configured model '$CONFIGURED_MODEL' not found - pulling now..."
                ollama pull "$CONFIGURED_MODEL"
                ok "Model '$CONFIGURED_MODEL' ready"
            fi
        else
            warn "No models downloaded yet - pulling '$CONFIGURED_MODEL'..."
            ollama pull "$CONFIGURED_MODEL"
            ok "Model '$CONFIGURED_MODEL' ready"
        fi
    else
        warn "Ollama installed but not running"
        echo "  Start it with: ollama serve"
    fi
else
    warn "Ollama not installed"
    echo "  Install: curl -fsSL https://ollama.com/install.sh | sh"
    echo "  Then: ollama serve"
    echo "  Then: ollama pull $CONFIGURED_MODEL"
fi

# Done
echo ""
echo "================================"
echo "  Setup complete!"
echo "================================"
echo ""
echo "To start empathySync:"
echo "  venv/bin/python -m streamlit run src/app.py"
echo ""
echo "Or if you installed with pip install -e .:"
echo "  empathysync"
echo ""
