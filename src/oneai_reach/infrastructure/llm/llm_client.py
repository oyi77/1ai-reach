import json
import os
import subprocess
import urllib.request
from typing import Optional

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.llm.anthropic_client import AnthropicClient
from oneai_reach.infrastructure.llm.gemini_client import GeminiClient


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.anthropic = AnthropicClient(settings)
        self.gemini = GeminiClient(settings)
        self.aitradepulse_api_key = settings.external_api.aitradepulse_api_key

    def _call_claude_cli(
        self, prompt: str, model: str = "sonnet", timeout: int = 60
    ) -> Optional[str]:
        try:
            result = subprocess.run(
                ["claude", "-p", "--model", model],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _call_opencode(
        self, prompt: str, model: str = "ollama-cloud/qwen3.5:397b", timeout: int = 60
    ) -> Optional[str]:
        try:
            result = subprocess.run(
                ["opencode", "run", "--model", model, "--", prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _call_ollama(self, prompt: str, model: str = "qwen2.5:7b") -> Optional[str]:
        try:
            data = json.dumps(
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                }
            ).encode()
            req = urllib.request.Request(
                "http://localhost:11434/v1/chat/completions",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return result["choices"][0]["message"]["content"]
        except Exception:
            pass
        return None

    def _call_groq(
        self, prompt: str, model: str = "llama-3.3-70b-versatile"
    ) -> Optional[str]:
        try:
            from groq import Groq

            key = os.getenv("GROQ_API_KEY")
            if not key:
                return None

            client = Groq(api_key=key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.7,
            )
            return resp.choices[0].message.content
        except Exception:
            pass
        return None

    def _call_openai(self, prompt: str, model: str = "gpt-4o-mini") -> Optional[str]:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return None
        try:
            data = json.dumps(
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.7,
                }
            ).encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return result["choices"][0]["message"]["content"]
        except Exception:
            pass
        return None

    def _call_aitradepulse(
        self, prompt: str, model: str = "auto/free-chat", timeout: int = 15
    ) -> Optional[str]:
        if not self.aitradepulse_api_key:
            return None
        try:
            data = json.dumps(
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.7,
                }
            ).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:20128/v1/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.aitradepulse_api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())
                return result["choices"][0]["message"]["content"]
        except Exception:
            pass
        return None

    def generate(self, prompt: str, fallback: Optional[str] = None) -> str:
        if result := self._call_aitradepulse(prompt, timeout=20):
            return result
        if result := self._call_opencode(prompt, timeout=15):
            return result
        if result := self._call_ollama(prompt):
            return result
        if result := self._call_claude_cli(prompt, timeout=15):
            return result
        if result := self.anthropic.generate(prompt):
            return result
        if result := self.gemini.generate(prompt):
            return result
        if result := self._call_groq(prompt):
            return result
        if result := self._call_openai(prompt):
            return result
        return (
            fallback
            or "Maaf Kak, lagi gangguan sedikit nih. Bisa ulangi pertanyaannya?"
        )

    def classify(self, prompt: str, fallback: str = "UNCLEAR") -> str:
        return self.generate(prompt, fallback)
