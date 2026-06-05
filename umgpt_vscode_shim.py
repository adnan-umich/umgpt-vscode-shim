"""
UM-GPT Toolkit <-> VS Code Copilot Custom Endpoint shim.

VS Code Custom Endpoint sends an API key as `x-api-key`.
UM-GPT Toolkit/Portkey expects `x-portkey-api-key`.

This shim accepts VS Code requests locally and forwards them to UM-GPT with
`x-portkey-api-key`, preserving the JSON body and streaming responses.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("umgpt-shim")

UPSTREAM_BASE_URL = os.getenv("UMGPT_UPSTREAM", "https://api.toolkit.umgpt.umich.edu").rstrip("/")
# Optional override. If set, this key is always used upstream.
# If unset, the incoming VS Code `x-api-key` value is forwarded as `x-portkey-api-key`.
UMGPT_API_KEY = os.getenv("UMGPT_API_KEY")
TIMEOUT_SECONDS = float(os.getenv("UMGPT_TIMEOUT", "300"))

app = FastAPI(title="UM-GPT VS Code Shim", version="1.0.0")

log.info("Shim starting — upstream=%s  auth_mode=%s",
         UPSTREAM_BASE_URL,
         "env UMGPT_API_KEY" if UMGPT_API_KEY else "incoming x-api-key")


def _build_forward_headers(request: Request, incoming_x_api_key: str | None) -> dict[str, str]:
    portkey_key = UMGPT_API_KEY or incoming_x_api_key
    if not portkey_key:
        raise ValueError(
            "Missing API key. Set UMGPT_API_KEY on the shim, or configure VS Code with an API key."
        )

    # Forward only safe/request-relevant headers. Do not forward host/auth/api-key headers.
    headers: dict[str, str] = {
        "content-type": request.headers.get("content-type", "application/json"),
        "accept": request.headers.get("accept", "application/json"),
        "x-portkey-api-key": portkey_key,
    }

    # Preserve streaming if the client asks for it.
    if "cache-control" in request.headers:
        headers["cache-control"] = request.headers["cache-control"]

    return headers


async def _stream_upstream_response(resp: httpx.Response) -> AsyncIterator[bytes]:
    async for chunk in resp.aiter_raw():
        yield chunk


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "upstream": UPSTREAM_BASE_URL,
        "auth_mode": "env UMGPT_API_KEY" if UMGPT_API_KEY else "incoming x-api-key -> x-portkey-api-key",
    }


@app.api_route("/v1/messages", methods=["POST", "OPTIONS"])
async def messages(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> Response:
    if request.method == "OPTIONS":
        return Response(status_code=204)

    try:
        headers = _build_forward_headers(request, x_api_key)
    except ValueError as exc:
        return JSONResponse(status_code=401, content={"error": str(exc)})

    body = await request.body()
    upstream_url = f"{UPSTREAM_BASE_URL}/v1/messages"

    # Log a summary of the incoming request.
    try:
        body_json = json.loads(body)
        model = body_json.get("model", "?")
        msgs = body_json.get("messages", [])
        last_role = msgs[-1].get("role", "?") if msgs else "?"
        last_content = msgs[-1].get("content", "") if msgs else ""
        preview = (last_content[:80] + "…") if len(str(last_content)) > 80 else last_content
        log.info(">>> RECEIVED  /v1/messages  model=%s  messages=%d  last[%s]=%r",
                 model, len(msgs), last_role, preview)
    except Exception:
        log.info(">>> RECEIVED  /v1/messages  body_bytes=%d", len(body))

    # Keep the client open for streamed responses. This matters for VS Code/Copilot.
    client = httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=30.0))
    req = client.build_request("POST", upstream_url, headers=headers, content=body)
    t0 = time.monotonic()
    try:
        upstream_resp = await client.send(req, stream=True)
    except Exception as exc:
        await client.aclose()
        log.error("<<< UPSTREAM ERROR  /v1/messages  error=%s", exc)
        return JSONResponse(status_code=502, content={"error": f"Failed to reach upstream: {exc}"})

    log.info("<<< UPSTREAM  /v1/messages  status=%d  content-type=%s  elapsed=%.2fs",
             upstream_resp.status_code,
             upstream_resp.headers.get("content-type", "?"),
             time.monotonic() - t0)

    response_headers = {}
    content_type = upstream_resp.headers.get("content-type", "application/json")
    if "text/event-stream" in content_type:
        response_headers["cache-control"] = "no-cache"

    async def streaming_body() -> AsyncIterator[bytes]:
        chunk_count = 0
        total_bytes = 0
        try:
            async for chunk in upstream_resp.aiter_raw():
                chunk_count += 1
                total_bytes += len(chunk)
                log.debug("    chunk #%d  bytes=%d  data=%r", chunk_count, len(chunk), chunk[:120])
                yield chunk
        finally:
            log.info("    STREAM DONE  chunks=%d  total_bytes=%d", chunk_count, total_bytes)
            await upstream_resp.aclose()
            await client.aclose()

    return StreamingResponse(
        streaming_body(),
        status_code=upstream_resp.status_code,
        media_type=content_type,
        headers=response_headers,
    )


# Optional compatibility route, only useful if you later point a Chat Completions client at the shim.
# It forwards unchanged to /v1/chat/completions upstream. Leave VS Code set to Messages for your current UM-GPT call.
@app.api_route("/v1/chat/completions", methods=["POST", "OPTIONS"])
async def chat_completions(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> Response:
    if request.method == "OPTIONS":
        return Response(status_code=204)

    try:
        headers = _build_forward_headers(request, x_api_key)
    except ValueError as exc:
        return JSONResponse(status_code=401, content={"error": str(exc)})

    body = await request.body()
    upstream_url = f"{UPSTREAM_BASE_URL}/v1/chat/completions"

    try:
        body_json = json.loads(body)
        model = body_json.get("model", "?")
        msgs = body_json.get("messages", [])
        log.info(">>> RECEIVED  /v1/chat/completions  model=%s  messages=%d", model, len(msgs))
    except Exception:
        log.info(">>> RECEIVED  /v1/chat/completions  body_bytes=%d", len(body))

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=30.0)) as client:
        try:
            r = await client.post(upstream_url, headers=headers, content=body)
        except Exception as exc:
            log.error("<<< UPSTREAM ERROR  /v1/chat/completions  error=%s", exc)
            return JSONResponse(status_code=502, content={"error": f"Failed to reach upstream: {exc}"})

    log.info("<<< UPSTREAM  /v1/chat/completions  status=%d  bytes=%d  elapsed=%.2fs",
             r.status_code, len(r.content), time.monotonic() - t0)

    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )
