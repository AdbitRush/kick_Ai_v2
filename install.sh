#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  Kickbacks Arbitrage — One-Command Installer
#  Tested on: Ubuntu 20.04+, Debian 11+, any systemd Linux
#
#  Usage:
#    bash install.sh                  # full install
#    bash install.sh --update         # pull latest code + restart services
#    bash install.sh --uninstall      # remove everything
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

REPO_URL="https://github.com/AdbitRush/Kick_and_backoff.git"
INSTALL_DIR="$HOME/kickbacks"
ENV_FILE="$INSTALL_DIR/.env"
TESTPROJ="$HOME/testproj"
BIN="$HOME/.local/bin/kickbacks"
NODE_MAJOR=20

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
BLU='\033[0;34m'; CYN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

banner() {
  echo ""
  echo -e "${CYN}${BOLD}╔═══════════════════════════════════════════╗${NC}"
  echo -e "${CYN}${BOLD}║   Kickbacks Arbitrage — Installer v1.0    ║${NC}"
  echo -e "${CYN}${BOLD}╚═══════════════════════════════════════════╝${NC}"
  echo ""
}

info()    { echo -e "${BLU}[→]${NC} $*"; }
ok()      { echo -e "${GRN}[✓]${NC} $*"; }
warn()    { echo -e "${YLW}[!]${NC} $*"; }
die()     { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}── $* ──────────────────────────────────────${NC}"; }

# ── Handle flags ──────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--update" ]]; then
  info "Pulling latest code..."
  git -C "$INSTALL_DIR" pull --ff-only
  ok "Updated."
  systemctl --user restart kickbacks-proxy kickbacks-brake 2>/dev/null || true
  ok "Services restarted."
  exit 0
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  warn "Removing Kickbacks Arbitrage..."
  systemctl --user stop kickbacks-proxy kickbacks-brake 2>/dev/null || true
  systemctl --user disable kickbacks-proxy kickbacks-brake 2>/dev/null || true
  rm -f "$HOME/.config/systemd/user/kickbacks-proxy.service"
  rm -f "$HOME/.config/systemd/user/kickbacks-brake.service"
  systemctl --user daemon-reload
  rm -f "$BIN"
  rm -rf "$INSTALL_DIR"
  ok "Uninstalled. Testproj at $TESTPROJ was left intact."
  exit 0
fi

banner

# ── OS check ──────────────────────────────────────────────────────────────────
section "System check"
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
  die "This installer requires Linux. On Windows use WSL2."
fi
if ! command -v systemctl &>/dev/null; then
  die "systemd required. This installer doesn't support SysV/OpenRC."
fi
ok "Linux + systemd detected"
info "User: $USER | Home: $HOME | Install dir: $INSTALL_DIR"

# ── System dependencies ───────────────────────────────────────────────────────
section "Installing system packages"

if command -v apt-get &>/dev/null; then
  PKG_MGR="apt-get"
  info "Detected apt (Ubuntu/Debian)"
  sudo apt-get update -qq
  sudo apt-get install -y -qq git curl python3 python3-pip build-essential ca-certificates gnupg lsb-release
elif command -v dnf &>/dev/null; then
  PKG_MGR="dnf"
  info "Detected dnf (Fedora/RHEL)"
  sudo dnf install -y git curl python3 gcc make ca-certificates
elif command -v yum &>/dev/null; then
  PKG_MGR="yum"
  info "Detected yum (CentOS/Amazon Linux)"
  sudo yum install -y git curl python3 gcc make ca-certificates
else
  die "Unsupported package manager. Install git, python3, curl, nodejs 18+ manually then re-run."
fi
ok "System packages installed"

# ── Node.js ──────────────────────────────────────────────────────────────────
section "Node.js $NODE_MAJOR"
if node --version 2>/dev/null | grep -qE "^v(1[89]|[2-9][0-9])"; then
  ok "Node.js already installed: $(node --version)"
else
  info "Installing Node.js $NODE_MAJOR via NodeSource..."
  if [[ "$PKG_MGR" == "apt-get" ]]; then
    curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | sudo -E bash - -qq
    sudo apt-get install -y -qq nodejs
  elif [[ "$PKG_MGR" == "dnf" ]]; then
    curl -fsSL https://rpm.nodesource.com/setup_${NODE_MAJOR}.x | sudo bash -
    sudo dnf install -y nodejs
  else
    curl -fsSL https://rpm.nodesource.com/setup_${NODE_MAJOR}.x | sudo bash -
    sudo yum install -y nodejs
  fi
  ok "Node.js installed: $(node --version)"
fi

# ── Claude Code CLI ───────────────────────────────────────────────────────────
section "Claude Code CLI"
if command -v claude &>/dev/null; then
  ok "Claude Code already installed: $(claude --version 2>/dev/null | head -1 || echo 'ok')"
else
  info "Installing Claude Code..."
  sudo npm install -g @anthropic-ai/claude-code
  ok "Claude Code installed"
fi

# ── Clone repo ────────────────────────────────────────────────────────────────
section "Kick_and_backoff repo"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  info "Repo already cloned — pulling latest..."
  git -C "$INSTALL_DIR" pull --ff-only
  ok "Updated"
else
  git clone "$REPO_URL" "$INSTALL_DIR"
  ok "Cloned to $INSTALL_DIR"
fi

# Install node deps (for worker/intd-v2.js)
info "Installing npm deps..."
npm install --prefix "$INSTALL_DIR" --silent
ok "npm deps ready"

# ── Test project ──────────────────────────────────────────────────────────────
section "Test project"
mkdir -p "$TESTPROJ/src"
if [[ ! -f "$TESTPROJ/src/index.js" ]]; then
  cat > "$TESTPROJ/src/index.js" <<'JS'
// DataProcessor — sample project for Claude queries
class DataProcessor {
  constructor(config = {}) {
    this.config = { batchSize: 100, timeout: 5000, retries: 3, ...config };
    this.queue = [];
    this.stats = { processed: 0, failed: 0, retried: 0 };
  }

  async process(items) {
    const batches = [];
    for (let i = 0; i < items.length; i += this.config.batchSize) {
      batches.push(items.slice(i, i + this.config.batchSize));
    }
    const results = await Promise.allSettled(batches.map(b => this._processBatch(b)));
    return results.map(r => r.status === 'fulfilled' ? r.value : null).filter(Boolean);
  }

  async _processBatch(batch) {
    for (let attempt = 0; attempt < this.config.retries; attempt++) {
      try {
        return await Promise.race([
          this._transform(batch),
          new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), this.config.timeout))
        ]);
      } catch (err) {
        this.stats.retried++;
        if (attempt === this.config.retries - 1) { this.stats.failed += batch.length; throw err; }
        await new Promise(r => setTimeout(r, 100 * Math.pow(2, attempt)));
      }
    }
  }

  async _transform(batch) {
    this.stats.processed += batch.length;
    return batch.map(item => ({ ...item, processed: true, ts: Date.now() }));
  }

  getStats() { return { ...this.stats, queueLength: this.queue.length }; }
}

module.exports = { DataProcessor };
JS
  cat > "$TESTPROJ/src/pipeline.js" <<'JS'
const { DataProcessor } = require('./index');

class Pipeline {
  constructor() {
    this.stages = [];
    this.processor = new DataProcessor({ batchSize: 50 });
  }
  addStage(fn) { this.stages.push(fn); return this; }
  async run(input) {
    let data = input;
    for (const stage of this.stages) {
      data = await stage(data);
    }
    return data;
  }
}

module.exports = { Pipeline };
JS
  cat > "$TESTPROJ/package.json" <<'JSON'
{"name":"testproj","version":"1.0.0","description":"Sample project for Claude queries","main":"src/index.js"}
JSON
  ok "Test project created at $TESTPROJ"
else
  ok "Test project already exists"
fi

# ── API keys setup ────────────────────────────────────────────────────────────
section "Configuration"

if [[ -f "$ENV_FILE" ]]; then
  warn ".env already exists at $ENV_FILE"
  read -rp "  Overwrite it? [y/N] " overwrite
  if [[ "${overwrite,,}" != "y" ]]; then
    info "Keeping existing .env"
    source "$ENV_FILE"
  fi
fi

if [[ ! -f "$ENV_FILE" ]] || [[ "${overwrite,,}" == "y" ]]; then
  echo ""
  echo -e "${BOLD}You need an OpenRouter API key.${NC}"
  echo "  Get one free at: https://openrouter.ai → Keys → Create Key"
  echo "  Free tier works — no credit card needed."
  echo ""
  while true; do
    read -rp "  OpenRouter API key (sk-or-...): " OR_KEY
    if [[ "$OR_KEY" == sk-or-* ]]; then break
    else warn "Should start with sk-or-  — try again"; fi
  done

  echo ""
  echo -e "${BOLD}Kickbacks CPM rate${NC} (from your Kickbacks.ai dashboard, default: 5.0)"
  read -rp "  CPM USD [5.0]: " CPM
  CPM="${CPM:-5.0}"

  cat > "$ENV_FILE" <<ENV
OPENROUTER_API_KEY=$OR_KEY
KICKBACKS_CPM=$CPM
ANTHROPIC_BASE_URL=http://127.0.0.1:5555
ANTHROPIC_AUTH_TOKEN=kickbacks-proxy
LEDGER_PATH=$HOME/kickbacks_ledger.jsonl
CLAUDE_WORKDIR=$TESTPROJ
PROXY_PORT=5555
ENV
  chmod 600 "$ENV_FILE"
  ok ".env written to $ENV_FILE"
fi

source "$ENV_FILE"

# ── Systemd services ──────────────────────────────────────────────────────────
section "Systemd services"
mkdir -p "$HOME/.config/systemd/user"

cat > "$HOME/.config/systemd/user/kickbacks-proxy.service" <<SVC
[Unit]
Description=Kickbacks Arbitrage Proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$(command -v python3) $INSTALL_DIR/proxy/arbitrage.py
Restart=always
RestartSec=5
StandardOutput=append:$HOME/kickbacks-proxy.log
StandardError=append:$HOME/kickbacks-proxy.log

[Install]
WantedBy=default.target
SVC

cat > "$HOME/.config/systemd/user/kickbacks-brake.service" <<SVC
[Unit]
Description=Kickbacks Coffee Brake Daemon
After=kickbacks-proxy.service
Requires=kickbacks-proxy.service

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStartPre=/bin/sleep 5
ExecStart=$(command -v python3) $INSTALL_DIR/scripts/coffee-brake.py --daemon
Restart=on-failure
RestartSec=30
StandardOutput=append:$HOME/kickbacks-brake.log
StandardError=append:$HOME/kickbacks-brake.log

[Install]
WantedBy=default.target
SVC

systemctl --user daemon-reload
systemctl --user enable kickbacks-proxy
ok "kickbacks-proxy.service enabled"

# Only enable brake if user wants it
echo ""
echo -e "${BOLD}Coffee Brake daemon${NC}"
echo "  Runs claude -p queries automatically while you work."
echo "  Only enable if you plan to be actively using Claude Code on this machine."
read -rp "  Enable coffee-brake daemon? [y/N] " enable_brake
if [[ "${enable_brake,,}" == "y" ]]; then
  systemctl --user enable kickbacks-brake
  ok "kickbacks-brake.service enabled"
else
  info "Coffee brake not enabled. Start manually: kickbacks brake-start"
fi

# Enable lingering so services survive logout (on servers)
if loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=no"; then
  sudo loginctl enable-linger "$USER" 2>/dev/null && ok "Linger enabled (services survive logout)" || \
    warn "Could not enable linger — services will stop on logout"
fi

# ── Start services ────────────────────────────────────────────────────────────
section "Starting services"
systemctl --user start kickbacks-proxy
sleep 2

# Health check
if curl -sf "http://127.0.0.1:${PROXY_PORT:-5555}/stats" &>/dev/null; then
  ok "Proxy is running and healthy"
  curl -s "http://127.0.0.1:${PROXY_PORT:-5555}/stats" | python3 -m json.tool 2>/dev/null | head -8 || true
else
  warn "Proxy started but not yet responding — check: kickbacks logs proxy"
fi

if [[ "${enable_brake,,}" == "y" ]]; then
  systemctl --user start kickbacks-brake
  ok "Coffee brake daemon started"
fi

# ── kickbacks CLI ─────────────────────────────────────────────────────────────
section "Installing kickbacks CLI"
mkdir -p "$HOME/.local/bin"

cat > "$BIN" <<'KICKBACKS'
#!/usr/bin/env bash
# kickbacks — management CLI
INSTALL_DIR="$HOME/kickbacks"
ENV_FILE="$INSTALL_DIR/.env"
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
PORT="${PROXY_PORT:-5555}"

case "${1:-help}" in
  start)
    systemctl --user start kickbacks-proxy
    [[ "${2:-}" == "--brake" ]] && systemctl --user start kickbacks-brake
    echo "Started. Check: kickbacks status"
    ;;
  stop)
    systemctl --user stop kickbacks-proxy kickbacks-brake 2>/dev/null
    echo "Stopped."
    ;;
  restart)
    systemctl --user restart kickbacks-proxy
    [[ "${2:-}" == "--brake" ]] && systemctl --user restart kickbacks-brake
    echo "Restarted."
    ;;
  status)
    echo "── Proxy ──────────────────────────────"
    systemctl --user status kickbacks-proxy --no-pager -l | head -8
    echo "── Coffee Brake ───────────────────────"
    systemctl --user status kickbacks-brake --no-pager -l 2>/dev/null | head -5 || echo "  (not enabled)"
    echo "── Live Stats ─────────────────────────"
    curl -sf "http://127.0.0.1:$PORT/stats" | python3 -m json.tool 2>/dev/null || echo "  Proxy not responding"
    ;;
  stats)
    curl -sf "http://127.0.0.1:$PORT/stats" | python3 -m json.tool || echo "Proxy not running"
    ;;
  dashboard)
    python3 "$INSTALL_DIR/tracker/dashboard.py"
    ;;
  report)
    python3 "$INSTALL_DIR/tracker/cost_report.py" "${@:2}"
    ;;
  snapshot)
    python3 "$INSTALL_DIR/tracker/current_cost_report.py"
    ;;
  logs)
    TARGET="${2:-proxy}"
    case "$TARGET" in
      proxy) tail -f "$HOME/kickbacks-proxy.log" ;;
      brake) tail -f "$HOME/kickbacks-brake.log" ;;
      *) echo "Usage: kickbacks logs [proxy|brake]" ;;
    esac
    ;;
  brake-start)
    systemctl --user start kickbacks-brake
    echo "Coffee brake started."
    ;;
  brake-stop)
    systemctl --user stop kickbacks-brake
    echo "Coffee brake stopped."
    ;;
  health)
    python3 "$INSTALL_DIR/scripts/health.py"
    ;;
  update)
    bash "$INSTALL_DIR/install.sh" --update
    ;;
  env)
    echo "Current .env:"
    cat "$ENV_FILE"
    ;;
  use)
    echo "Add these to your shell session:"
    echo ""
    echo "  export ANTHROPIC_BASE_URL=http://127.0.0.1:$PORT"
    echo "  export ANTHROPIC_AUTH_TOKEN=kickbacks-proxy"
    echo ""
    echo "Then run: claude"
    ;;
  help|*)
    echo "kickbacks — Arbitrage management CLI"
    echo ""
    echo "  kickbacks start          Start proxy (add --brake for coffee brake)"
    echo "  kickbacks stop           Stop all services"
    echo "  kickbacks restart        Restart proxy"
    echo "  kickbacks status         Service status + live stats"
    echo "  kickbacks stats          Live proxy stats (JSON)"
    echo "  kickbacks dashboard      Full P&L dashboard"
    echo "  kickbacks snapshot       Quick cost/revenue snapshot"
    echo "  kickbacks report         Per-query detail (--date YYYY-MM-DD --csv out.csv)"
    echo "  kickbacks logs proxy     Tail proxy log"
    echo "  kickbacks logs brake     Tail coffee brake log"
    echo "  kickbacks brake-start    Start coffee brake daemon"
    echo "  kickbacks brake-stop     Stop coffee brake daemon"
    echo "  kickbacks health         Quick proxy health check"
    echo "  kickbacks use            Print env vars to paste into your terminal"
    echo "  kickbacks update         Pull latest code + restart"
    echo "  kickbacks env            Show current .env"
    ;;
esac
KICKBACKS

chmod +x "$BIN"

# Add ~/.local/bin to PATH if not already there
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
  SHELL_RC="$HOME/.bashrc"
  [[ -f "$HOME/.zshrc" ]] && SHELL_RC="$HOME/.zshrc"
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
  export PATH="$HOME/.local/bin:$PATH"
  info "Added ~/.local/bin to PATH in $SHELL_RC"
fi
ok "kickbacks CLI installed at $BIN"

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${CYN}${BOLD}╔═════════════════════════════════════════════════╗${NC}"
echo -e "${CYN}${BOLD}║              Installation Complete               ║${NC}"
echo -e "${CYN}${BOLD}╚═════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}Proxy running at:${NC}   http://127.0.0.1:${PROXY_PORT:-5555}"
echo -e "${BOLD}Installed to:${NC}       $INSTALL_DIR"
echo -e "${BOLD}Ledger:${NC}             ${LEDGER_PATH:-$HOME/kickbacks_ledger.jsonl}"
echo -e "${BOLD}Logs:${NC}               $HOME/kickbacks-proxy.log"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo ""
echo -e "  ${GRN}1.${NC} Sign into Kickbacks.ai inside Claude Code:"
echo -e "     ${YLW}kickbacks use${NC}   — prints the env vars to paste"
echo -e "     Then run: ${YLW}claude${NC}"
echo ""
echo -e "  ${GRN}2.${NC} Use Claude Code normally — ads run in the spinner"
echo ""
echo -e "  ${GRN}3.${NC} Track earnings:"
echo -e "     ${YLW}kickbacks dashboard${NC}   — full P&L"
echo -e "     ${YLW}kickbacks snapshot${NC}    — quick numbers"
echo -e "     ${YLW}kickbacks stats${NC}       — live proxy JSON"
echo ""
echo -e "  ${GRN}4.${NC} Management:"
echo -e "     ${YLW}kickbacks status${NC}      — service health"
echo -e "     ${YLW}kickbacks logs proxy${NC}  — live log"
echo -e "     ${YLW}kickbacks update${NC}      — pull latest"
echo ""
echo -e "${YLW}Note:${NC} Open a new terminal (or run: source ~/.bashrc) for 'kickbacks' to be in PATH"
echo ""
