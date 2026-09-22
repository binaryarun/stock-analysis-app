#!/data/data/com.termux/files/usr/bin/bash
# Autostart script for Termux:Boot (https://f-droid.org/packages/com.termux.boot/).
# Install Termux:Boot, then copy this file to ~/.termux/boot/ollama.sh
# and chmod +x it. Termux:Boot will run every script in that directory
# after the device reboots, so Ollama comes back up without manual steps.

termux-wake-lock
OLLAMA_KEEP_ALIVE=30m nohup ollama serve > "$HOME/ollama.log" 2>&1 &
