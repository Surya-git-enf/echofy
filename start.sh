#!/bin/bash

echo "🚀 Booting Modular AI God-Mode..."

# ==========================================
# Install Core Dependencies
# ==========================================
echo "📦 Installing core tools..."

rm -rf "$(npm root -g)/@anthropic-ai" 2>/dev/null || true

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

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
  https://github.com/Surya-git-enf/Claude-skills.git "$TEMP_DIR"; then

    find "$TEMP_DIR" -type f -iname "*.md" \
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
fi

if [ ! -f .env.example ]; then
    cp .env .env.example 2>/dev/null || touch .env.example
fi

# ==========================================
# Restart Proxy
# ==========================================
echo "⚡ Starting proxy..."

pkill -f python || true
pkill -f fcc-server || true

"$HOME/.local/bin/fcc-server" > proxy.log 2>&1 &
sleep 5

# ==========================================
# Health Check
# ==========================================
if curl -s http://127.0.0.1:8082 >/dev/null; then
    echo "✅ Proxy server running on port 8082"
else
    echo "❌ Proxy startup failed"
    cat proxy.log
fi

# ==========================================
# Launch Claude
# ==========================================
echo "🚀 Launching Claude..."

chmod +x "$(which claude 2>/dev/null)" 2>/dev/null || true

npx -y @anthropic-ai/claude-code \
  --continue \
  --dangerously-skip-permissions
claude
