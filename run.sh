#!/usr/bin/env bash
set -euo pipefail

# Option A: let VS Code pass the key via x-api-key and shim forwards it as x-portkey-api-key.
# Option B: uncomment this and store the real key here or in your shell profile.
# export UMGPT_API_KEY="paste-your-real-umgpt-portkey-key"

export UMGPT_UPSTREAM="${UMGPT_UPSTREAM:-https://api.toolkit.umgpt.umich.edu}"
export UMGPT_TIMEOUT="${UMGPT_TIMEOUT:-300}"

exec uvicorn umgpt_vscode_shim:app --host 127.0.0.1 --port 8787
