"""Thin OpenAI-compatible client for the LM Studio local server."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class LLMError(Exception):
    """Raised when the LM Studio server is unreachable or returns a bad payload."""


class LMStudioClient:
    def __init__(self, base_url: str = "http://localhost:1234/v1", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise LLMError(f"HTTP {e.code} from LM Studio at {url}") from e
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", None) or e
            raise LLMError(f"could not connect to LM Studio at {url}: {reason}") from e

    def models(self) -> list[str]:
        data = self._request("GET", "/models")
        ids = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
        return [i for i in ids if i]

    def chat(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._request("POST", "/chat/completions", payload)
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"no choices in response from model {model}")
        content = (choices[0].get("message") or {}).get("content")
        if content is None:
            raise LLMError(f"no message content in response from model {model}")
        return str(content).strip()
