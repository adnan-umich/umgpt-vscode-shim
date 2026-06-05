#!/usr/bin/env bash
set -euo pipefail

curl http://127.0.0.1:8787/v1/messages \
  -H 'Content-Type: application/json' \
  -H "x-api-key: $UMGPT_API_KEY" \
  -d '{
    "model": "gpt-5.5",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "test"}
    ]
  }' --output -