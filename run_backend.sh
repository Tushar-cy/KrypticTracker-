#!/bin/bash
# Wrapper script to run backend with correct Python path

cd "$(dirname "$0")"
export PYTHONPATH="venv/lib/python3.12/site-packages:$PYTHONPATH"
venv/bin/python backend/app.py




