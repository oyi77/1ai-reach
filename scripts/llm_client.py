import os
import subprocess
import urllib.request
import json

GROQ_AVAILABLE = False
try:
    from groq import Groq as _Groq

    GROQ_AVAILABLE = True
except ImportError:
    pass


def _call_claude(prompt, model="sonnet", timeout=60):
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


def _call_opencode(prompt, model="ollama-cloud/qwen3.5:397b", timeout=60):
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


def _call_ollama(prompt, model="qwen2.5:7b"):
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


def _call_groq(prompt, model="llama-3.3-70b-versatile"):
    if not GROQ_AVAILABLE:
        return None
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        client = _Groq(api_key=key)
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


def _call_openai(prompt, model="gpt-4o-mini"):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        import urllib.request

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


def _call_aitradepulse(prompt, model="auto/free-chat", timeout=15):
    key = os.getenv("AITRADEPULSE_API_KEY", "sk-f0c1ddf471008e76-501723-c663b4ac")
    if not key:
        return None
    try:
        import urllib.request

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
                "Authorization": f"Bearer {key}",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        pass
    return None


def generate(prompt, fallback=None):
    if result := _call_aitradepulse(prompt, timeout=20):
        return result
    if result := _call_opencode(prompt, timeout=15):
        return result
    if result := _call_ollama(prompt):
        return result
    if result := _call_claude(prompt, timeout=15):
        return result
    if result := _call_groq(prompt):
        return result
    if result := _call_openai(prompt):
        return result
    return fallback or "Maaf, saya sedang tidak bisa menjawab saat ini."


def classify(prompt, fallback="UNCLEAR"):
    return generate(prompt, fallback)
