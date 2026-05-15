"""
Multi-provider HTTP adapters for kiki ingest.

Each provider implements `call(system: str, user: str, schema: dict) -> Result`
where Result is `(parsed_json: dict, usage: dict)`. The `usage` dict carries
provider-reported numbers when available — typically input/output tokens and a
`cost_usd` estimate (computed via a small built-in price table since not all
providers report cost in the response).

Stdlib only — no requests, no SDKs. Uses urllib.request + json.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


class ProviderError(RuntimeError):
    """Raised on auth/network/decoding failures so the orchestrator can
    print a single clean error line instead of a stack trace."""


# Per-million-token pricing (USD). Used purely to surface a cost estimate
# in the output line; not authoritative — providers move prices around.
PRICES = {
    "claude-opus-4-7":      (15.00, 75.00),
    "claude-sonnet-4-6":    (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "gpt-5":                (1.25, 10.00),
    "gpt-4.1":              (2.00, 8.00),
    "gpt-4o-mini":          (0.15, 0.60),
    "gemini-2.5-pro":       (1.25, 10.00),
    "gemini-2.5-flash":     (0.30, 2.50),
}


def _estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    p = PRICES.get(model)
    if not p:
        return 0.0
    in_per_m, out_per_m = p
    return (in_tokens / 1_000_000) * in_per_m + (out_tokens / 1_000_000) * out_per_m


def _http_post(url: str, headers: dict, body: dict, timeout: int = 180) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {e.code} from {url}: {body_text[:500]}") from None
    except urllib.error.URLError as e:
        raise ProviderError(f"network error to {url}: {e.reason}") from None
    except TimeoutError:
        raise ProviderError(f"timed out after {timeout}s waiting for {url}") from None
    except json.JSONDecodeError as e:
        raise ProviderError(f"non-JSON response from {url}: {e}") from None


# ──────────────────────────────────────────────────────────────────────────────
# Anthropic
# ──────────────────────────────────────────────────────────────────────────────

def call_anthropic(model: str, system: str, user: str, schema: dict, *,
                   api_key: str) -> tuple[dict, dict]:
    """Anthropic Messages API. Force JSON via a single tool definition; the
    model's only valid action is to call that tool with our schema as input."""
    if not api_key:
        raise ProviderError("anthropic: no API key (set ANTHROPIC_API_KEY)")
    body = {
        "model": model,
        "max_tokens": 8192,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "tools": [{
            "name": "submit_ingest_plan",
            "description": "Submit the structured ingest plan.",
            "input_schema": schema,
        }],
        "tool_choice": {"type": "tool", "name": "submit_ingest_plan"},
    }
    resp = _http_post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        body=body,
    )
    tool_input = None
    for block in resp.get("content", []) or []:
        if block.get("type") == "tool_use" and block.get("name") == "submit_ingest_plan":
            tool_input = block.get("input")
            break
    if tool_input is None:
        raise ProviderError(f"anthropic: no tool_use in response: {json.dumps(resp)[:500]}")
    usage = resp.get("usage", {})
    in_t = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
    out_t = usage.get("output_tokens", 0)
    return tool_input, {
        "input_tokens": in_t,
        "output_tokens": out_t,
        "cost_usd": _estimate_cost(model, in_t, out_t),
    }


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI
# ──────────────────────────────────────────────────────────────────────────────

def call_openai(model: str, system: str, user: str, schema: dict, *,
                api_key: str, base_url: str = "https://api.openai.com/v1") -> tuple[dict, dict]:
    """OpenAI Chat Completions with response_format=json_schema (strict mode)."""
    if not api_key:
        raise ProviderError("openai: no API key (set OPENAI_API_KEY)")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "ingest_plan",
                "strict": True,
                "schema": schema,
            },
        },
    }
    resp = _http_post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body=body,
    )
    try:
        text = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise ProviderError(f"openai: malformed response: {e}: {json.dumps(resp)[:500]}") from None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProviderError(f"openai: response was not JSON: {e}: {text[:500]}") from None
    usage = resp.get("usage", {})
    in_t = usage.get("prompt_tokens", 0)
    out_t = usage.get("completion_tokens", 0)
    return parsed, {
        "input_tokens": in_t,
        "output_tokens": out_t,
        "cost_usd": _estimate_cost(model, in_t, out_t),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Google Gemini
# ──────────────────────────────────────────────────────────────────────────────

def call_gemini(model: str, system: str, user: str, schema: dict, *,
                api_key: str) -> tuple[dict, dict]:
    """Gemini generateContent with responseSchema. Gemini's response schema
    rejects 'additionalProperties' and a few other JSON Schema keywords —
    we strip them defensively."""
    if not api_key:
        raise ProviderError("gemini: no API key (set GEMINI_API_KEY)")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _gemini_clean_schema(schema),
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    resp = _http_post(url, headers={"Content-Type": "application/json"}, body=body)
    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ProviderError(f"gemini: malformed response: {e}: {json.dumps(resp)[:500]}") from None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProviderError(f"gemini: response was not JSON: {e}: {text[:500]}") from None
    usage = resp.get("usageMetadata", {})
    in_t = usage.get("promptTokenCount", 0)
    out_t = usage.get("candidatesTokenCount", 0)
    return parsed, {
        "input_tokens": in_t,
        "output_tokens": out_t,
        "cost_usd": _estimate_cost(model, in_t, out_t),
    }


def _gemini_clean_schema(s: Any) -> Any:
    if isinstance(s, dict):
        out = {}
        for k, v in s.items():
            if k in ("additionalProperties", "$schema", "title"):
                continue
            out[k] = _gemini_clean_schema(v)
        return out
    if isinstance(s, list):
        return [_gemini_clean_schema(x) for x in s]
    return s


# ──────────────────────────────────────────────────────────────────────────────
# Ollama (local)
# ──────────────────────────────────────────────────────────────────────────────

def call_ollama(model: str, system: str, user: str, schema: dict, *,
                base_url: str = "http://localhost:11434") -> tuple[dict, dict]:
    """Local Ollama. Uses format=json (loose JSON mode). Quality varies wildly
    by model; we ask the model to emit the schema in the system prompt because
    Ollama doesn't accept a JSON schema directly."""
    schema_blurb = (
        "\n\nReturn ONLY valid JSON matching this schema (no markdown, no prose):\n"
        + json.dumps(schema, indent=2)
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system + schema_blurb},
            {"role": "user", "content": user},
        ],
        "format": "json",
        "stream": False,
    }
    # Local models are slow on big prompts; give a generous ceiling.
    resp = _http_post(f"{base_url}/api/chat",
                      headers={"Content-Type": "application/json"},
                      body=body, timeout=600)
    try:
        text = resp["message"]["content"]
    except KeyError as e:
        raise ProviderError(f"ollama: malformed response: {e}: {json.dumps(resp)[:500]}") from None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProviderError(f"ollama: response was not JSON: {e}: {text[:500]}") from None
    in_t = resp.get("prompt_eval_count", 0)
    out_t = resp.get("eval_count", 0)
    return parsed, {
        "input_tokens": in_t,
        "output_tokens": out_t,
        "cost_usd": 0.0,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Dispatch
# ──────────────────────────────────────────────────────────────────────────────

PROVIDERS = {
    "anthropic": ("call_anthropic", "claude-opus-4-7"),
    "openai":    ("call_openai",    "gpt-5"),
    "gemini":    ("call_gemini",    "gemini-2.5-pro"),
    "ollama":    ("call_ollama",    "llama3.1:8b"),
}


def call(provider: str, model: str, system: str, user: str, schema: dict,
         *, provider_config: dict) -> tuple[dict, dict]:
    if provider not in PROVIDERS:
        raise ProviderError(f"unknown provider: {provider} (known: {', '.join(PROVIDERS)})")
    fn = globals()[PROVIDERS[provider][0]]
    if provider == "anthropic":
        return fn(model, system, user, schema, api_key=provider_config.get("api_key", ""))
    if provider == "openai":
        return fn(model, system, user, schema,
                  api_key=provider_config.get("api_key", ""),
                  base_url=provider_config.get("base_url", "https://api.openai.com/v1"))
    if provider == "gemini":
        return fn(model, system, user, schema, api_key=provider_config.get("api_key", ""))
    if provider == "ollama":
        return fn(model, system, user, schema,
                  base_url=provider_config.get("base_url", "http://localhost:11434"))
    raise ProviderError(f"no dispatcher for {provider}")  # unreachable
