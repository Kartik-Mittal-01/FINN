"""Model-provider interface. The rest of the app only ever calls `get_llm()`.

* OllamaProvider  – local, free. Used when an Ollama server is reachable.
* NullProvider    – no model. Every caller has a deterministic fallback and labels its output accordingly.

Add another provider (llama.cpp server, vLLM, ...) by implementing `LLMProvider` and registering it in `get_llm()`.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from ..config import settings

log = logging.getLogger(__name__)


class LLMProvider(ABC):
    name = "none"
    model = ""

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def generate(self, prompt: str, system: str = "", json_mode: bool = False, max_tokens: int = 400,
                 temperature: float = 0.1) -> str: ...

    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}" if self.model else self.name


class NullProvider(LLMProvider):
    name = "none"

    def available(self) -> bool:
        return False

    def generate(self, *a, **k) -> str:
        raise RuntimeError("No LLM configured")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, url: str, model: str):
        self.url = url.rstrip("/")
        self.model = model
        self._checked_at = 0.0
        self._ok = False

    def available(self) -> bool:
        if time.time() - self._checked_at < 30:
            return self._ok
        self._checked_at = time.time()
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=1.5)
            tags = [m.get("name", "") for m in r.json().get("models", [])]
            base = self.model.split(":")[0]
            self._ok = r.status_code == 200 and any(t == self.model or t.split(":")[0] == base for t in tags)
            if r.status_code == 200 and not self._ok:
                log.warning("Ollama is running but model %s is not pulled (have: %s)", self.model, tags)
        except Exception:
            self._ok = False
        return self._ok

    def generate(self, prompt: str, system: str = "", json_mode: bool = False, max_tokens: int = 400,
                 temperature: float = 0.1) -> str:
        payload = {"model": self.model, "prompt": prompt, "system": system, "stream": False,
                   "options": {"temperature": temperature, "num_predict": max_tokens}}
        if json_mode:
            payload["format"] = "json"
        r = httpx.post(f"{self.url}/api/generate", json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "").strip()


_provider: Optional[LLMProvider] = None


def get_llm() -> LLMProvider:
    global _provider
    if _provider is None:
        mode = settings.llm_provider.lower()
        if mode == "none":
            _provider = NullProvider()
        else:  # auto | ollama
            _provider = OllamaProvider(settings.ollama_url, settings.ollama_model)
    return _provider


def reset_llm():  # used by tests
    global _provider
    _provider = None
