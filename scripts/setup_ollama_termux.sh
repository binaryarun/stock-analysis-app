#!/data/data/com.termux/files/usr/bin/bash
# Run this INSIDE Termux on the Pixel 10 (not on your Mac).
#
# One-time setup of a local Ollama server on Android for the app's
# optional "Explain this" feature. Ollama serves on localhost:11434,
# which the Flet app (built via `flet build apk`) reaches the same way
# it does on desktop — no code changes needed, only the server side
# differs per-platform.
#
# Usage:
#   1. Install Termux from F-Droid or GitHub releases (NOT the Play
#      Store build, which is unmaintained and blocked from some installs).
#   2. Copy this script onto the device (e.g. via `termux-setup-storage`
#      + moving it into ~/downloads, or `curl`/`git clone` this repo).
#   3. chmod +x setup_ollama_termux.sh && ./setup_ollama_termux.sh
set -euo pipefail

echo "== Updating Termux packages =="
pkg update -y && pkg upgrade -y

echo "== Installing prerequisites =="
pkg install -y wget termux-api proot

echo "== Acquiring wake lock (stops Android from killing the process) =="
termux-wake-lock

OLLAMA_ARCH="$(uname -m)"
echo "== Detected architecture: ${OLLAMA_ARCH} =="

if [ ! -f "$PREFIX/bin/ollama" ]; then
  echo "== Downloading Ollama Linux ARM64 binary =="
  # Official Ollama Linux release tarball; extracts to ./bin/ollama, ./lib/ollama
  wget -O ollama-linux-arm64.tgz \
    "https://ollama.com/download/ollama-linux-arm64.tgz"
  tar -C "$PREFIX" -xzf ollama-linux-arm64.tgz
  rm ollama-linux-arm64.tgz
else
  echo "== Ollama binary already present, skipping download =="
fi

echo "== Starting ollama serve in the background =="
OLLAMA_KEEP_ALIVE=30m nohup ollama serve > "$HOME/ollama.log" 2>&1 &
sleep 3

echo "== Pulling a small instruct model (adjust if resource-constrained) =="
ollama pull qwen2.5:3b-instruct || ollama pull qwen:2b

echo "== Done. Verifying server responds =="
curl -sf http://localhost:11434/api/tags && echo "" && echo "Ollama is reachable."

cat <<'EOF'

Next steps:
  - To keep this alive across reboots, install Termux:Boot (F-Droid) and
    drop a start script in ~/.termux/boot/ that runs `termux-wake-lock`
    then `ollama serve &`.
  - Termux itself must stay running in the background — disable battery
    optimization for Termux in Android Settings > Apps > Termux > Battery.
  - The app's health check hits http://localhost:11434/api/tags; as long
    as this script's final curl succeeded, the "Explain this" button will
    appear automatically inside the app, no extra configuration needed.
EOF
