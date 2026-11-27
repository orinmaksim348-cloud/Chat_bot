"""Асинхронный клиент ИИ для Flet-мессенджера.

Поддерживает:
1. Google Gemini API (бесплатный тариф в Google AI Studio) — через GEMINI_API_KEY.
2. Любой OpenAI-совместимый API (OpenRouter, Groq, OpenAI, DeepSeek и др.) — через AI_API_KEY + AI_BASE_URL.
3. Автономный резервный режим, если API-ключи ещё не заданы.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


@dataclass
class AIConfig:
    provider: str = "auto"  # "auto" | "gemini" | "openai"
    gemini_api_key: str = ""
    gemini_model: str = DEFAULT_GEMINI_MODEL
    openai_api_key: str = ""
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    openai_model: str = DEFAULT_OPENAI_MODEL

    @classmethod
    def from_env(cls) -> "AIConfig":
        return cls(
            provider=os.getenv("AI_PROVIDER", "auto").strip().lower() or "auto",
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL,
            openai_api_key=os.getenv("AI_API_KEY", "").strip(),
            openai_base_url=os.getenv("AI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip() or DEFAULT_OPENAI_BASE_URL,
            openai_model=os.getenv("AI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL,
        )

    def resolved_provider(self) -> str:
        if self.provider == "gemini" and self.gemini_api_key:
            return "gemini"
        if self.provider == "openai" and self.openai_api_key:
            return "openai"
        if self.gemini_api_key:
            return "gemini"
        if self.openai_api_key:
            return "openai"
        return "offline"


async def generate_ai_reply(
    config: AIConfig,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
) -> tuple[str, str]:
    """Возвращает кортеж (текст_ответа, источник_ответа)."""
    provider = config.resolved_provider()

    if provider == "gemini":
        try:
            reply = await _call_gemini(config, system_prompt, history, user_text)
            return reply, f"Gemini ({config.gemini_model})"
        except Exception as exc:
            return (
                f"Не удалось получить ответ от Gemini API: {exc}\n\n"
                "Проверьте GEMINI_API_KEY и модель в настройках.",
                "error",
            )

    if provider == "openai":
        try:
            reply = await _call_openai_compatible(config, system_prompt, history, user_text)
            return reply, f"AI ({config.openai_model})"
        except Exception as exc:
            return (
                f"Не удалось получить ответ от AI API: {exc}\n\n"
                "Проверьте AI_BASE_URL, AI_API_KEY и имя модели в настройках.",
                "error",
            )

    return _offline_fallback(user_text), "offline"


async def _call_gemini(
    config: AIConfig,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.gemini_model}:generateContent"
    )
    contents: list[dict[str, Any]] = []
    for msg in history[-12:]:
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        role = "user" if msg.get("sender") == "out" else "model"
        contents.append({"role": role, "parts": [{"text": text}]})

    if not contents or contents[-1]["role"] != "user":
        contents.append({"role": "user", "parts": [{"text": user_text}]})

    payload: dict[str, Any] = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
        },
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(
            url,
            params={"key": config.gemini_api_key},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    candidates = data.get("candidates") or []
    if not candidates:
        raise ValueError("Пустой ответ от модели")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise ValueError("Модель вернула пустой текст")
    return text


async def _call_openai_compatible(
    config: AIConfig,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
) -> str:
    base = config.openai_base_url.rstrip("/")
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in history[-12:]:
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        role = "user" if msg.get("sender") == "out" else "assistant"
        messages.append({"role": role, "content": text})

    if messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": user_text})

    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.openai_model,
        "messages": messages,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Пустой ответ от AI API")
    content = (choices[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise ValueError("Модель вернула пустой текст")
    return content.strip()


def _offline_fallback(user_text: str) -> str:
    lower = user_text.strip().lower()
    if lower in {"/help", "помощь", "команды"}:
        return (
            "Сейчас работает локальный демо-режим (API-ключ ещё не задан).\n\n"
            "Чтобы включить настоящий ИИ:\n"
            "1. Откройте «Настройки» (иконка шестерёнки сверху) и вставьте бесплатный GEMINI_API_KEY из Google AI Studio или ключ OpenRouter/Groq/OpenAI.\n"
            "2. На хостинге (Render / Hugging Face Spaces) добавьте GEMINI_API_KEY в переменные окружения."
        )
    if any(w in lower for w in ("привет", "здравствуй", "хай", "hello")):
        return (
            "Привет! Я готов к работе. Добавь GEMINI_API_KEY или AI_API_KEY в настройках "
            "(шестерёнка в шапке), и я начну отвечать через реальную нейросеть."
        )
    if any(w in lower for w in ("хостинг", "деплой", "render", "выложить")):
        return (
            "Этот Flet-проект уже готов к бесплатному деплою:\n"
            "• Render (Free Web Service) — подключите GitHub-репозиторий, файл render.yaml настроит всё сам.\n"
            "• Hugging Face Spaces (Docker SDK) — загрузите файлы проекта и задайте GEMINI_API_KEY в Secrets."
        )
    return (
        f"Получил сообщение: «{user_text[:100]}».\n\n"
        "ИИ-ключ пока не подключён — откройте настройки (шестерёнка) и укажите "
        "GEMINI_API_KEY (бесплатный в Google AI Studio) или OpenAI-совместимый ключ."
    )
