from __future__ import annotations

import json
import os
from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel

from agents.reasoning_logger import log_reasoning_step

ProviderName = Literal["gemini", "groq"]
T = TypeVar("T", bound=BaseModel)


def _prefer() -> ProviderName:
    v = (os.getenv("LLM_PROVIDER") or "groq").strip().lower()
    return "gemini" if v == "gemini" else "groq"


def _gemini_api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


async def _gemini_complete(prompt: str, system: str, max_tokens: int) -> str:
    api_key = _gemini_api_key()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY or GOOGLE_API_KEY")

    parts: list[dict[str, Any]] = [{"text": prompt}]
    if system:
        parts.insert(0, {"text": f"System:\n{system}\n\nUser task below."})

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.35, "maxOutputTokens": max_tokens},
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        res = await client.post(url, params={"key": api_key}, json=payload)
        res.raise_for_status()
        data = res.json()

    candidates = data.get("candidates") or []
    texts: list[str] = []
    for c in candidates:
        content = (c or {}).get("content") or {}
        for p in content.get("parts") or []:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                texts.append(p["text"])
    text = "\n".join([t.strip() for t in texts if t and t.strip()]).strip()
    if not text:
        raise RuntimeError("Gemini returned empty text")
    return text


async def _groq_complete(prompt: str, system: str, max_tokens: int) -> str:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY")

    model = (os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
    url = "https://api.groq.com/openai/v1/chat/completions"
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0.35,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        res = await client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
        res.raise_for_status()
        data = res.json()

    choices = data.get("choices") or []
    msg = (((choices[0] or {}).get("message") or {}).get("content") if choices else "") or ""
    text = str(msg).strip()
    if not text:
        raise RuntimeError("Groq returned empty text")
    return text


async def chat_complete(
    prompt: str,
    system: str = "",
    max_tokens: int = 850,
    workflow_id: str | None = None,
    agent_name: str | None = None,
) -> tuple[str, str]:
    """
    Single entry for LLM completion. Primary model from LLM_PROVIDER (gemini | groq).
    On primary failure, tries the other provider and logs a reasoning step when workflow context is present.
    Returns (text, provider_used).
    """
    primary = _prefer()
    secondary: ProviderName = "groq" if primary == "gemini" else "gemini"
    wf = (workflow_id or "").strip()
    ag = (agent_name or "").strip() or "assessment_agent"

    async def _run(which: ProviderName) -> str:
        if which == "gemini":
            return await _gemini_complete(prompt, system, max_tokens)
        return await _groq_complete(prompt, system, max_tokens)

    try:
        text = await _run(primary)
        return text, primary
    except Exception:
        text = await _run(secondary)
        if wf:
            log_reasoning_step(
                wf,
                ag,
                "llm_fallback",
                f"Primary LLM ({primary}) failed; completed request with {secondary}. "
                f"LLM_PROVIDER={primary}.",
                "fallback",
                {"primary": primary, "used": secondary},
            )
        return text, secondary


def _extract_json_block(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start : end + 1]
    raise ValueError("No JSON object found in model response")


async def structured_complete(
    *,
    prompt: str,
    output_model: type[T],
    system: str = "",
    workflow_id: str | None = None,
    agent_name: str | None = None,
    max_tokens: int = 1200,
) -> T:
    schema = output_model.model_json_schema()
    augmented_prompt = (
        f"{prompt}\n\n"
        "Return only one valid JSON object. Do not include markdown fences.\n"
        f"JSON schema:\n{json.dumps(schema)}"
    )
    text, _provider = await chat_complete(
        augmented_prompt,
        system=system,
        max_tokens=max_tokens,
        workflow_id=workflow_id,
        agent_name=agent_name,
    )
    payload = _extract_json_block(text)
    return output_model.model_validate_json(payload)
