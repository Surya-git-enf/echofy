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
# Install Persistent Project Skills
# ==========================================
echo "🧠 Installing requested Claude Skills into persistent workspace..."

# Install List 1 (Kept: Strix, Agent Reach, Setup)
npx -y skills add usestrix/strix -y
npx -y skills add Panniantong/agent-reach -y
npx -y skills add https://github.com/anthropics/claude-plugins-official/tree/main/plugins/claude-code-setup -y

# Install List 2 (Kept: TasteSkill, Web Guidelines, Image to Code, Awesome Design)
npx -y skills add https://www.tasteskill.dev/ -y
npx -y skills add https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines -y
npx -y skills add https://github.com/Leonxlnx/taste-skill/tree/main/skills/image-to-code-skill -y
npx -y skills add VoltAgent/awesome-design-md -y

# Install List 3 (Kept: Find Skills, Superpowers, Task Observer)
npx -y skills add vercel-labs/skills -y
npx -y skills add obra/superpowers -y
npx -y skills add rebelytics/one-skill-to-rule-them-all -y
npx -y skills add cosmix/loom

# Install Additional Request
npx -y skills add latent-spaces/brag -y

echo "✅ All skills installed to local .claude/skills directory"

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
  
