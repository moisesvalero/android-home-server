# AGENTS.md — Instructions for Autonomous AI Agents

> **For AI Coding Agents:** Claude Code, Cursor, Antigravity, OpenCode, Codex, Windsurf, GitHub Copilot CLI, Aider, and similar LLM-driven agents.
> 
> **Goal:** Deploy, configure, and maintain the **Android Home Server** stack on any Android smartphone (running Termux) completely or semi-autonomously with minimal human friction.

---

## 1. System Overview & Architecture

You are tasked with turning an Android phone into an ultra-low-power, 24/7 home server.

```text
┌──────────────────────────────────────────────────────────┐
│                   ANDROID SMARTPHONE                     │
│               (Android 8.0+ / Termux aarch64)            │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │                        PM2                         │  │
│  │               (Process Daemon 24/7)                │  │
│  └───────┬────────────────────┬──────────────────┬────┘  │
│          │                    │                  │       │
│          ▼                    ▼                  ▼       │
│  ┌───────────────┐    ┌───────────────┐    ┌──────────┐  │
│  │ Hermes Agent  │    │ MiniDLNA +    │    │ Crons &  │  │
│  │ (Telegram Bot)│    │ Dashboard 8090│    │ Watchdog │  │
│  └───────┬───────┘    └───────┬───────┘    └────┬─────┘  │
└──────────┼────────────────────┼─────────────────┼────────┘
           │ (Polling HTTPS)    │ (LAN HTTP/DLNA) │
           ▼                    ▼                 ▼
     Telegram API          Smart TV / PC     Battery Guard
```

- **Runtime Environment:** Termux userland (rootless). Root access is **NOT** required.
- **Process Manager:** PM2 supervising Python & Node.js daemons with auto-resurrection on phone reboot via `Termux:Boot`.
- **Networking:**
  - **Hermes AI Bot:** Outbound HTTPS long-polling to Telegram (`core.telegram.org/bots`). **Zero port forwarding** needed on home router.
  - **Media Server & Dashboard:** Local LAN HTTP on port `8090` and DLNA SSDP broadcast (port `1900/udp` + media port `8200/tcp`).
  - **SSH (optional):** Port `8022/tcp`, strictly local LAN or VPN (Tailscale/WireGuard).

---

## 2. Interaction Modes for AI Agents

Determine your execution mode based on your current environment:

### Mode A: Direct Remote Agent (SSH / ADB) — Full Autonomy
*If you have SSH access (`ssh -p 8022 user@phone-ip`) or ADB (`adb shell`):*
1. Execute shell commands directly on the phone.
2. Inspect hardware telemetry, install dependencies, inject `.env`, and start services.
3. Verify outputs with zero manual copy-pasting required from the user.

### Mode B: Co-Pilot Agent (Host Machine / Chat Interface) — Assisted Autonomy
*If you are running on the user's desktop/laptop without direct phone access:*
1. Prompt the user **only** for the essential variables:
   - Telegram Bot Token (from `@BotFather`)
   - Telegram User ID (from `@userinfobot` — critical for bot authorization)
   - Preferred LLM provider (`deepseek`, `openai`, `groq`, or `openrouter`) and API Key.
2. Generate clean, copy-pasteable blocks for the user to run in Termux.
3. If the user has SSH enabled, use `deploy.sh` to push scripts from their computer to the phone.

---

## 3. Step-by-Step Autonomous Execution Playbook

Follow these sequential steps when setting up the server:

### Phase 1: Pre-Flight Android Health Check
Verify that the device and Termux are ready. Run or ask the user to run:

```bash
# 1. Acquire CPU wake-lock so Android doesn't suspend Termux when screen is OFF
termux-wake-lock

# 2. Check architecture and storage
uname -m          # Expecting aarch64 (or armv7l)
df -h "$HOME"     # Ensure at least 3-5 GB free storage

# 3. Check battery status via Termux:API
termux-battery-status
```

> **Crucial Rule:** If `termux-battery-status` fails, install `termux-api` package (`pkg install termux-api`) and ensure the user installed the **Termux:API companion APK** from F-Droid.

---

### Phase 2: Clone and Setup Workspace

```bash
pkg update -y && pkg install -y git
git clone https://github.com/moisesvalero/android-home-server.git "$HOME/.hermes-server"
cd "$HOME/.hermes-server"
```

---

### Phase 3: Configuration (`.env`)

Generate `$HOME/.hermes-server/.env` based on `.env.example`. Ask or configure:

```bash
cat << 'EOF' > "$HOME/.hermes-server/.env"
# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN="<USER_TELEGRAM_BOT_TOKEN>"
ALLOWED_TELEGRAM_USERS="<USER_NUMERIC_TELEGRAM_ID>"

# LLM Provider Configuration
# Options: deepseek | openai | groq | openrouter | ollama
DEFAULT_LLM_PROVIDER="deepseek"
DEFAULT_LLM_MODEL="deepseek-flash"

# Provider API Keys
DEEPSEEK_API_KEY="<USER_DEEPSEEK_API_KEY>"
OPENAI_API_KEY=""
GROQ_API_KEY=""
OPENROUTER_API_KEY=""

# Local Ollama endpoint (if running on a PC in the same Wi-Fi)
OLLAMA_BASE_URL="http://192.168.1.100:11434/v1"

# Storage & Ports
MEDIA_DIR="$HOME/media"
DASHBOARD_PORT=8090
DLNA_FRIENDLY_NAME="Android Media Server"

# Battery Protection Thresholds
BATTERY_MIN_THRESHOLD=25
BATTERY_MAX_TEMP_CELSIUS=45
EOF
```

---

### Phase 4: Automated Installation

Execute `install.sh`:

```bash
chmod +x install.sh
./install.sh
```

**What `install.sh` handles autonomously:**
1. Sets `export ANDROID_API_LEVEL=31` to avoid compile-time issues with native C/Rust extensions.
2. Installs required Termux packages (`python`, `nodejs-lts`, `minidlna`, `pm2`, native wheels).
3. Creates Python virtualenv at `$HOME/.hermes-venv`.
4. Deploys scripts to `$HOME/.hermes/`.
5. Sets up persistence hook in `$HOME/.termux/boot/start-services.sh`.
6. Registers and starts all services in PM2.

---

### Phase 5: Verification & Diagnostics

Run the verification checklist to confirm everything is operational:

```bash
# 1. Check PM2 processes
pm2 status

# Expected output:
# ┌──────────────────┬──────────┬────────┬──────┬───────────┐
# │ name             │ mode     │ status │ cpu  │ memory    │
# ├──────────────────┼──────────┼────────┼──────┼───────────┤
# │ dlna-server      │ fork     │ online │ 0%   │ ~17 MB    │
# │ media-dashboard  │ fork     │ online │ 0%   │ ~35 MB    │
# │ hermes           │ fork     │ online │ 0%   │ ~45 MB    │
# └──────────────────┴──────────┴────────┴──────┴───────────┘

# 2. Test Media Dashboard HTTP endpoint
curl -I http://localhost:8090

# 3. Test Battery Watchdog
python3 "$HOME/.hermes/cron/cron_battery_guard.py"

# 4. Inspect logs for any initialization errors
pm2 logs --lines 20 --nostream
```

---

### Phase 6: Hardware-Level Battery Safeguard Checklist

Remind the user of the **50% Battery Strategy**:
1. Connect the phone charger to a cheap mechanical or smart plug timer.
2. Program it to charge for **30 to 45 minutes twice a day** (e.g. 08:00 and 20:00).
3. The battery guard watchdog will alert over Telegram if:
   - Battery falls below 25% (unplugged or failed timer).
   - Battery temperature exceeds 45°C (thermal throttling or overheating).

---

## 4. Common Agent Troubleshooting Matrix

| Issue | Root Cause | Solution for the Agent |
| :--- | :--- | :--- |
| `termux-battery-status` hangs or errors | Missing companion app | Run `pkg install termux-api` and instruct user to install `Termux:API` APK from F-Droid. |
| PM2 lost after phone reboot | `Termux:Boot` not configured | Verify `$HOME/.termux/boot/start-services.sh` has `+x` permissions and open the Termux:Boot app once manually. |
| `pip install cryptography` or `lxml` fails | Native C/Rust compile error on ARM64 | Run `pkg install python-cryptography python-lxml python-psutil` to use pre-compiled Termux binaries. |
| Process killed after screen is turned off | Android OEM Doze / Battery Optimization | Run `termux-wake-lock`. Instruct user to set Termux Battery to "Unrestricted" in Android Settings. |
| Smart TV does not discover MiniDLNA | Firewall / Wi-Fi Client Isolation | Verify TV and phone are on the same Wi-Fi band/SSID without AP Isolation. Restart DLNA: `pm2 restart dlna-server`. |
| Telegram Bot doesn't reply | Wrong Bot Token or non-matching User ID | Check `pm2 logs hermes`. Verify `ALLOWED_TELEGRAM_USERS` matches the user's numeric Telegram ID. |

---

## 5. Security Principles for AI Agents

1. **Never commit `.env` or credentials:** Keep `.env` strictly local on the device.
2. **Restrict SSH:** Ensure SSH in Termux listens only on local Wi-Fi. Never suggest opening port 8022 on a home router without a secure VPN (Tailscale/WireGuard).
3. **Whitelist Telegram ID:** Never leave `ALLOWED_TELEGRAM_USERS` empty in production, as anyone could message the bot and consume LLM tokens.
