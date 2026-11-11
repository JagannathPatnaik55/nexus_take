"""Optional read-only OpenAI-compatible productivity assistant."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from nexus.config import setting


def configured() -> bool:
    return bool(setting("OPENAI_API_KEY", secret_path=("ai", "api_key"), default=""))


def ask_assistant(prompt: str, context: str) -> str:
    api_key = setting("OPENAI_API_KEY", secret_path=("ai", "api_key"), default="")
    if not api_key:
        raise RuntimeError("AI is disabled until an API key is configured in Streamlit secrets.")
    model = setting("OPENAI_MODEL", secret_path=("ai", "model"), default="gpt-4.1-mini")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are NEXUS, a read-only personal productivity assistant. Clearly separate observations from suggestions. Never claim a change was made."},
            {"role": "user", "content": f"Stored context (may be incomplete):\n{context}\n\nRequest:\n{prompt}"},
        ],
        "temperature": 0.4,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("The AI provider could not be reached. Check your connection and try again.") from exc
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError("The AI provider returned an unexpected response.") from exc
    return str(result["choices"][0]["message"]["content"])

