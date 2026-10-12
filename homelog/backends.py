"""Model backends.

HomeLog talks to models through the Ollama chat API. On a laptop that is Ollama
(http://localhost:11434). On the ASUS UGen300, Hailo provides Hailo-Ollama, an
Ollama-compatible server built on HailoRT (default http://localhost:8000), so the
same client code can point at the accelerator in Stage II.

StubBackend returns fixed placeholder text so the pipeline and demo page can be
tested without any model installed. Stub output is always marked as such.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import requests


class Backend:
    name = "base"

    def chat(self, prompt: str, image_jpeg: bytes | None = None, system: str | None = None) -> str:
        raise NotImplementedError


@dataclass
class OllamaBackend(Backend):
    base_url: str
    model: str
    timeout: float = 180.0
    temperature: float = 0.2
    max_tokens: int = 0          # 0 = no cap
    name: str = "ollama"

    def chat(self, prompt: str, image_jpeg: bytes | None = None, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        user = {"role": "user", "content": prompt}
        if image_jpeg is not None:
            # The image only ever exists in memory: base64 in the request body.
            user["images"] = [base64.b64encode(image_jpeg).decode("ascii")]
        messages.append(user)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,  # Qwen3 models: answer directly, no reasoning trace
            "options": {"temperature": self.temperature},
        }
        if self.max_tokens:
            payload["options"]["num_predict"] = self.max_tokens
        r = requests.post(f"{self.base_url.rstrip('/')}/api/chat", json=payload, timeout=self.timeout)
        if r.status_code == 400 and "think" in r.text:
            # Older servers (or models) that do not accept the "think" flag.
            payload.pop("think")
            r = requests.post(f"{self.base_url.rstrip('/')}/api/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        msg = r.json().get("message", {})
        content = (msg.get("content") or "").strip()
        if not content and msg.get("thinking"):
            # A "thinking" model spent its whole budget reasoning and never answered.
            print(f"   warning: {self.model} returned only reasoning, no answer. "
                  f"Use an instruct model (see config.yaml).")
        return content


class StubBackend(Backend):
    """Placeholder model for testing the plumbing. Never use its output in a demo."""

    name = "stub"

    def __init__(self):
        self._n = 0

    def chat(self, prompt: str, image_jpeg: bytes | None = None, system: str | None = None) -> str:
        self._n += 1
        if image_jpeg is not None:
            return f"[stub] Placeholder description #{self._n} ({len(image_jpeg)} bytes seen)."
        return "[stub] Placeholder daily summary. Run with an Ollama backend for real output."


def make_backend(cfg: dict, role: str) -> Backend:
    """role is 'vlm' or 'llm'."""
    if cfg.get("backend") == "stub":
        return StubBackend()
    section = cfg[role]
    return OllamaBackend(base_url=section.get("base_url", cfg.get("base_url", "http://localhost:11434")),
                         model=section["model"],
                         timeout=float(section.get("timeout", 180)),
                         max_tokens=int(section.get("max_tokens", 0)))
