# UM-GPT VS Code Shi
m

This shim lets VS Code Copilot Custom Endpoint talk to UM-GPT Toolkit when VS Code sends:


```http
x-api-key: YOUR_KEY
```

but UM-GPT/Portkey expects:

```http
x-portkey-api-key: YOUR_KEY
```

## Install

```bash
cd umgpt-vscode-shim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

### Recommended mode: key stored in VS Code

The shim forwards VS Code's `x-api-key` as `x-portkey-api-key`:

```bash
./run.sh
```

### Alternative mode: key stored in the shim environment

This ignores VS Code's key and always uses `UMGPT_API_KEY` upstream:

```bash
export UMGPT_API_KEY='paste-your-real-umgpt-portkey-key'
./run.sh
```

## Test

```bash
curl http://127.0.0.1:8787/healthz
```

Then test Messages:

```bash
curl http://127.0.0.1:8787/v1/messages \
  -H 'Content-Type: application/json' \
  -H "x-api-key: $API_KEY" \
  -d '{
    "model": "gpt-5.5",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "test"}
    ]
  }'
```

## VS Code Custom Endpoint

Use the local shim URL, not the UM-GPT URL directly:

```json
[
  {
    "name": "UM GPT Toolkit",
    "vendor": "customendpoint",
    "apiKey": "paste-your-real-umgpt-portkey-key",
    "apiType": "messages",
    "models": [
      {
        "id": "gpt-5.5",
        "name": "UM GPT 5.5",
        "url": "http://127.0.0.1:8787/v1/messages",
        "toolCalling": false,
        "vision": false,
        "maxInputTokens": 128000,
        "maxOutputTokens": 8192
      }
    ]
  }
]
```

Keep `toolCalling` off until plain chat works.
