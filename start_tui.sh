#!/bin/bash

# KrypticTrack - Quick Start Script

echo "🧠 KrypticTrack - Your Laptop Brain"
echo "===================================="
echo ""

# Check if LM Studio is running
if curl -s http://localhost:1234/v1/models > /dev/null 2>&1; then
    echo "✅ LM Studio is running"
else
    echo "⚠️  LM Studio is not running"
    echo "   Start LM Studio and load a model for full AI features"
    echo "   URL: http://localhost:1234"
fi

echo ""
echo "Launching TUI Dashboard..."
echo ""

# Run TUI
python3 tui_dashboard.py
