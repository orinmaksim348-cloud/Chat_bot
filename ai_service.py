"""Асинхронный клиент ИИ для Flet-мессенджера.

Поддерживает без лишних настроек:
1. GigaChat API (Сбер) — GIGACHAT_CREDENTIALS (OAuth + https://api.giga.chat/v1/chat/completions).
2. Google Gemini API — GEMINI_API_KEY:
   - автоматически работает как с ключами Google AI Studio (generativelanguage.googleapis.com),
   - так и с ключами Vertex AI Express Mode с префиксом AQ. (aiplatform.googleapis.com),
   - передаёт ключ только в заголовке x-goog-api-key (ключ не попадает в URL и текст ошибок).
3. Любой OpenAI-совместимый API — AI_API_KEY + AI_BASE_URL.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


GIGACHAT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://api.giga.chat/v1/chat/completions"
DEFAULT_GIGACHAT_MODEL = "GigaChat-2"
DEFAULT_GIGACHAT_SCOPE = "GIGACHAT_API_PERS"

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


@dataclass
class AIConfig:
    provider: str = "auto"  # "auto" | "gigachat" | "gemini" | "openai"
    # GigaChat
    gigachat_credentials: str = ""
    gigachat_scope: str = DEFAULT_GIGACHAT_SCOPE
    gigachat_model: str = DEFAULT_GIGACHAT_MODEL
    gigachat_verify_ssl: bool = False
    gigachat_ca_bundle: str = ""
    # Gemini / Vertex Express
    gemini_api_key: str = ""
    gemini_model: str = DEFAULT_GEMINI_MODEL
    # OpenAI-compatible
    openai_api_key: str = ""
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    openai_model: str = DEFAULT_OPENAI_MODEL

    # Кеш OAuth-токена GigaChat (30 мин)
    _giga_token: str = ""
    _giga_expires_at: float = 0.0

    @classmethod
    def from_env(cls) -> "AIConfig":
        verify_raw = os.getenv("GIGACHAT_VERIFY_SSL_CERTS", "false").strip().lower()
        return cls(
            provider=os.getenv("AI_PROVIDER", "auto").strip().lower() or "auto",
            gigachat_credentials=os.getenv("GIGACHAT_CREDENTIALS", "").strip(),
            gigachat_scope=os.getenv("GIGACHAT_SCOPE", DEFAULT_GIGACHAT_SCOPE).strip() or DEFAULT_GIGACHAT_SCOPE,
            gigachat_model=os.getenv("GIGACHAT_MODEL", DEFAULT_GIGACHAT_MODEL).strip() or DEFAULT_GIGACHAT_MODEL,
            gigachat_verify_ssl=verify_raw in {"1", "true", "yes"},
            gigachat_ca_bundle=os.getenv("GIGACHAT_CA_BUNDLE_FILE", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL,
            openai_api_key=os.getenv("AI_API_KEY", "").strip(),
            openai_base_url=os.getenv("AI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip() or DEFAULT_OPENAI_BASE_URL,
            openai_model=os.getenv("AI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL,
        )

    def resolved_provider(self) -> str:
        if self.provider == "gigachat" and self.gigachat_credentials:
            return "gigachat"
        if self.provider == "gemini" and self.gemini_api_key:
            return "gemini"
        if self.provider == "openai" and self.openai_api_key:
            return "openai"
        if self.gigachat_credentials:
            return "gigachat"
        if self.gemini_api_key:
            return "gemini"
        if self.openai_api_key:
            return "openai"
        return "offline"

    def invalidate_giga_token(self) -> None:
        self._giga_token = ""
        self._giga_expires_at = 0.0


async def generate_ai_reply(
    config: AIConfig,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
) -> tuple[str, str]:
    """Возвращает кортеж (текст_ответа, источник)."""
    provider = config.resolved_provider()

    if provider == "gigachat":
        try:
            reply = await _call_gigachat(config, system_prompt, history, user_text)
            return reply, f"GigaChat ({config.gigachat_model})"
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            detail = _extract_error_message(exc.response)
            return (
                f"Ошибка GigaChat API (HTTP {code}): {detail}\n\n"
                "Проверьте GIGACHAT_CREDENTIALS, scope (GIGACHAT_API_PERS / B2B / CORP) и модель.",
                "error",
            )
        except Exception as exc:
            return f"Не удалось подключиться к GigaChat API: {type(exc).__name__}: {exc}", "error"

    if provider == "gemini":
        try:
            reply = await _call_gemini(config, system_prompt, history, user_text)
            return reply, f"Gemini ({config.gemini_model})"
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            detail = _extract_error_message(exc.response)
            return (
                f"Ошибка Gemini API (HTTP {code}): {detail}\n\n"
                "Проверьте GEMINI_API_KEY и выбранную модель в настройках.",
                "error",
            )
        except Exception as exc:
            return f"Не удалось подключиться к Gemini API: {type(exc).__name__}: {exc}", "error"

    if provider == "openai":
        try:
            reply = await _call_openai_compatible(config, system_prompt, history, user_text)
            return reply, f"AI ({config.openai_model})"
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            detail = _extract_error_message(exc.response)
            return f"Ошибка AI API (HTTP {code}): {detail}", "error"
        except Exception as exc:
            return f"Не удалось подключиться к AI API: {type(exc).__name__}: {exc}", "error"

    return _offline_fallback(user_text), "offline"


def _extract_error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
            if data.get("message"):
                return str(data["message"])
    except Exception:
        pass
    return resp.reason_phrase or "ошибка запроса"


async def _get_giga_token(config: AIConfig, client: httpx.AsyncClient) -> str:
    now = time.time()
    if config._giga_token and now < (config._giga_expires_at - 60):
        return config._giga_token

    resp = await client.post(
        GIGACHAT_OAUTH_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {config.gigachat_credentials}",
        },
        data={"scope": config.gigachat_scope},
    )
    resp.raise_for_status()
    data = resp.json()

    token = data.get("access_token")
    if not token:
        raise ValueError("GigaChat OAuth не вернул access_token")

    raw_exp = float(data.get("expires_at") or 0)
    if raw_exp > 1e12:
        raw_exp /= 1000.0
    if raw_exp <= now:
        raw_exp = now + 1700.0

    config._giga_token = token
    config._giga_expires_at = raw_exp
    return token


async def _call_gigachat(
    config: AIConfig,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
) -> str:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in history[-12:]:
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        role = "user" if msg.get("sender") == "out" else "assistant"
        messages.append({"role": role, "content": text})
    if messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": user_text})

    payload = {
        "model": config.gigachat_model,
        "messages": messages,
        "temperature": 0.7,
    }
    verify: bool | str = config.gigachat_ca_bundle or config.gigachat_verify_ssl

    async with httpx.AsyncClient(timeout=30.0, verify=verify) as client:
        token = await _get_giga_token(config, client)
        resp = await client.post(
            GIGACHAT_API_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json=payload,
        )
        if resp.status_code == 401:
            config.invalidate_giga_token()
            token = await _get_giga_token(config, client)
            resp = await client.post(
                GIGACHAT_API_URL,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                json=payload,
            )
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices") or []
    content = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    if not content:
        raise ValueError("GigaChat вернул пустой ответ")
    return content


async def _call_gemini(
    config: AIConfig,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
) -> str:
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
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
        },
    }

    model = config.gemini_model or DEFAULT_GEMINI_MODEL
    key = config.gemini_api_key

    # Ключи с префиксом AQ. могут относиться к Vertex AI Express Mode (aiplatform.googleapis.com)
    # или к Google AI Studio (generativelanguage.googleapis.com). Пробуем подходящий первым,
    # а при 403/404 автоматически переключаемся на альтернативный эндпоинт.
    vertex_url = f"https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent"
    studio_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    urls = [vertex_url, studio_url] if key.startswith("AQ.") else [studio_url, vertex_url]

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": key,
    }

    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for idx, url in enumerate(urls):
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code in {403, 404} and idx < len(urls) - 1:
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                continue
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise ValueError("Пустой ответ от Gemini")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
            if not text:
                raise ValueError("Gemini вернул пустой текст")
            return text

    if last_exc is not None:
        raise last_exc
    raise ValueError("Не удалось выполнить запрос к Gemini API")


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

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {config.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.openai_model,
                "messages": messages,
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices") or []
    content = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    if not content:
        raise ValueError("AI API вернул пустой текст")
    return content


def _offline_fallback(user_text: str) -> str:
    return (
        f"Получил сообщение: «{user_text[:100]}».\n\n"
        "API-ключ ещё не подключён. Откройте настройки (шестерёнка сверху) или добавьте в Render:\n"
        "• GIGACHAT_CREDENTIALS — для GigaChat (Сбер)\n"
        "• GEMINI_API_KEY — для Google Gemini / Vertex AI Express Mode"
    )
