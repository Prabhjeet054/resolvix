"""Ollama HTTP API client with health checks and chat completion."""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


class OllamaClient:
    """Thin client around the Ollama REST API (`/api/tags`, `/api/chat`)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_sec: float = 2.0,
        chat_timeout_sec: float = 120.0,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.timeout_sec = timeout_sec
        self.chat_timeout_sec = chat_timeout_sec

    def is_available(self) -> bool:
        """Return True if Ollama responds to GET /api/tags within timeout."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/tags",
                timeout=self.timeout_sec,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List locally available model tags. Empty list if offline."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/tags",
                timeout=self.timeout_sec,
            )
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models") or []
            names: list[str] = []
            for item in models:
                name = item.get("name") or item.get("model")
                if name:
                    names.append(str(name))
            return names
        except Exception:
            return []

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        """Send a chat completion request. Returns assistant text or raises RuntimeError."""
        temp = (
            temperature
            if temperature is not None
            else float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
        )
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temp},
        }
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.chat_timeout_sec,
            )
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message") or {}
            content = message.get("content")
            if not content:
                raise RuntimeError("Ollama returned an empty response")
            return str(content).strip()
        except requests.RequestException as exc:
            raise RuntimeError(f"Ollama chat failed: {exc}") from exc
