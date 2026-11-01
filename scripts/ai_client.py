#!/usr/bin/env python3
"""Optional OpenAI-compatible client for Radar-News AI translation and editorial scoring.

Enabled only when AI_API_KEY and AI_MODEL are configured. Never silently sends news to
an external service without an explicit repository secret. All callers must retain fallback
behavior when the provider is unavailable.
"""
import json
import os
import urllib.request
import urllib.error

def configured():
    return bool(os.getenv("AI_API_KEY") and os.getenv("AI_MODEL"))

def _base_url():
    return (os.getenv("AI_API_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

def chat_json(system_prompt, user_payload, max_tokens=3000, timeout=45):
    """Call an OpenAI-compatible chat-completions endpoint and return parsed JSON."""
    if not configured():
        raise RuntimeError("AI disabled: configure AI_API_KEY and AI_MODEL repository secrets")
    body = {
        "model": os.environ["AI_MODEL"],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
        ]
    }
    req = urllib.request.Request(
        _base_url() + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + os.environ["AI_API_KEY"],
            "Content-Type": "application/json",
            "User-Agent": "Radar-News/AI-quality"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", "replace")
        raise RuntimeError("AI provider HTTP %s: %s" % (exc.code, detail)) from exc
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("AI provider returned no choices")
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    content = str(content).strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    result = json.loads(content)
    if not isinstance(result, dict):
        raise RuntimeError("AI provider response must be a JSON object")
    return result
