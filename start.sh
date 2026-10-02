#!/bin/bash

echo "🚀 Booting Modular AI God-Mode..."

# ==========================================
# Install Core Dependencies
# ==========================================
echo "📦 Installing core tools..."

# Remove old Anthropic CLI package if present
rm -rf "$(npm root -g)/@anthropic-ai" 2>/dev/null || true

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Make uv available immediately
export PATH="$HOME/.local/bin:$PATH"

# Install Claude Code
npm install -g @anthropic-ai/claude-code

# ==========================================
# Install Python & AI Engine
# ==========================================
echo "⚙️ Installing AI engine..."

uv python install 3.14

uv tool install --force --python 3.14 \
  git+https://github.com/Alishahryar1/free-claude-code.git

# ==========================================
# Sync Claude Skills
# ==========================================
echo "🧠 Syncing Claude Skills..."

rm -rf ~/.claude/skills
mkdir -p ~/.claude/skills

TEMP_DIR=$(mktemp -d)

if git clone --quiet --depth 1 \
  https://github.com/Surya-git-enf/Claude-skills.git \
  "$TEMP_DIR"; then

    find "$TEMP_DIR" \
      -type f \
      -iname "*.md" \
      -exec cp {} ~/.claude/skills/ \;

    echo "✅ Skills synced successfully"
else
    echo "❌ Failed to sync skills"
fi

rm -rf "$TEMP_DIR"

# ==========================================
# Configure Environment
# ==========================================
export ANTHROPIC_AUTH_TOKEN="freecc"
export ANTHROPIC_BASE_URL="http://127.0.0.1:8082"

# Persist environment variables
grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' ~/.bashrc || \
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

grep -qxF 'export ANTHROPIC_AUTH_TOKEN="freecc"' ~/.bashrc || \
echo 'export ANTHROPIC_AUTH_TOKEN="freecc"' >> ~/.bashrc

grep -qxF 'export ANTHROPIC_BASE_URL="http://127.0.0.1:8082"' ~/.bashrc || \
echo 'export ANTHROPIC_BASE_URL="http://127.0.0.1:8082"' >> ~/.bashrc

# ==========================================
# Load Local Environment Variables
# ==========================================
if [ -f .env ]; then
    echo "📂 Loading .env variables..."

    set -a
    source .env
    set +a
else
    echo "⚠️ .env file not found"
fi

# Create .env.example if missing
if [ ! -f .env.example ]; then
    if [ -f .env ]; then
        cp .env .env.example
    else
        touch .env.example
    fi
fi

# ==========================================
# Restart Proxy
# ==========================================
echo "⚡ Starting proxy..."

# Stop only the proxy if it is already running
pkill -f fcc-server 2>/dev/null || true

# Start proxy
"$HOME/.local/bin/fcc-server" > proxy.log 2>&1 &

PROXY_PID=$!

echo "Proxy PID: $PROXY_PID"

# Give proxy time to start
sleep 5

# ==========================================
# Health Check
# ==========================================
if curl -s --max-time 5 \
  http://127.0.0.1:8082 >/dev/null 2>&1; then

    echo "✅ Proxy server running on port 8082"

else

    echo "❌ Proxy startup failed"

    if [ -f proxy.log ]; then
        echo "---------- proxy.log ----------"
        cat proxy.log
        echo "--------------------------------"
    fi

fi

# ==========================================
# Launch Claude
# ==========================================
echo "🚀 Launching Claude..."

# Ensure Claude executable
CLAUDE_PATH="$(which claude 2>/dev/null || true)"

if [ -n "$CLAUDE_PATH" ]; then
    chmod +x "$CLAUDE_PATH" 2>/dev/null || true
fi

echo ""
echo "=========================================="
echo "📁 Workspace: $(pwd)"
echo "=========================================="
echo ""

# Launch Claude only once
claude \
  --continue \
  --dangerously-skip-permissions
