#!/bin/bash
# KrypticTrack TUI Launcher

cd "$(dirname "$0")"

echo "🧠 Starting KrypticTrack TUI..."
echo ""
python3 ktui.py

echo ""
echo "Session ended. Check reports/ for exported data."
