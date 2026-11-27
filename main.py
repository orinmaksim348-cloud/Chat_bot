"""PulseChat — WhatsApp-подобный мессенджер с ИИ-чат-ботом на Flet 1.0."""

from __future__ import annotations

import datetime
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import flet as ft
from dotenv import load_dotenv

from ai_service import (
    AIConfig,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    generate_ai_reply,
)

load_dotenv()


THEMES = {
    "dark": {
        "bg_app": "#0b141a",
        "bg_sidebar": "#111b21",
        "bg_header": "#202c33",
        "bg_input": "#2a3942",
        "bg_hover": "#202c33",
        "bg_active": "#2a3942",
        "bubble_out": "#005c4b",
        "bubble_in": "#202c33",
        "border": "#222d34",
        "text_primary": "#e9edef",
        "text_secondary": "#8696a0",
        "accent": "#00a884",
        "check_read": "#53bdeb",
        "badge_text": "#111b21",
    },
    "light": {
        "bg_app": "#efeae2",
        "bg_sidebar": "#ffffff",
        "bg_header": "#f0f2f5",
        "bg_input": "#ffffff",
        "bg_hover": "#f5f6f6",
        "bg_active": "#e9edef",
        "bubble_out": "#d9fdd3",
        "bubble_in": "#ffffff",
        "border": "#e2e8f0",
        "text_primary": "#111b21",
        "text_secondary": "#54656f",
        "accent": "#008069",
        "check_read": "#53bdeb",
        "badge_text": "#ffffff",
    },
}


def now_hhmm() -> str:
    return datetime.datetime.now().strftime("%H:%M")


@dataclass
class ChatRoom:
    id: str
    name: str
    avatar_text: str
    color: str
    is_bot: bool
    status: str
    system_prompt: str = ""
    unread: int = 0
    quick_prompts: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


def create_default_chats() -> list[ChatRoom]:
    t = now_hhmm()
    return [
        ChatRoom(
            id="ai-assistant",
            name="ИИ-Ассистент",
            avatar_text="AI",
            color="#00a884",
            is_bot=True,
            status="в сети · нейросеть",
            system_prompt=(
                "Ты полезный и лаконичный ИИ-ассистент внутри мессенджера PulseChat. "
                "Отвечай по делу, структурированно и на русском языке."
            ),
            quick_prompts=[
                "Придумай 5 идей для пет-проекта на Python",
                "Объясни REST API простыми словами",
                "Как выложить этот мессенджер на бесплатный хостинг?",
            ],
            messages=[
                {
                    "id": uuid.uuid4().hex,
                    "sender": "in",
                    "text": (
                        "Привет! Я ИИ-бот на базе Flet. Напиши любой вопрос — "
                        "или нажми на одну из быстрых подсказок ниже."
                    ),
                    "time": t,
                    "read": True,
                }
            ],
        ),
        ChatRoom(
            id="ai-coder",
            name="Код-Ментор ИИ",
            avatar_text="PY",
            color="#2b6cb0",
            is_bot=True,
            status="в сети · Python / Flet",
            system_prompt=(
                "Ты опытный Python и Flet разработчик. Помогай с кодом, дебагом, "
                "архитектурой и деплоем. Пиши кратко и с рабочими примерами."
            ),
            quick_prompts=[
                "Как добавить SQLite к Flet-приложению?",
                "Покажи пример асинхронного запроса через httpx",
            ],
            messages=[
                {
                    "id": uuid.uuid4().hex,
                    "sender": "in",
                    "text": "Привет! Помогу с Python, Flet 1.0, API и деплоем. Что разбираем?",
                    "time": t,
                    "read": False,
                }
            ],
            unread=1,
        ),
        ChatRoom(
            id="ai-support",
            name="Бот Поддержки",
            avatar_text="П",
            color="#805ad5",
            is_bot=True,
            status="в сети · менеджер",
            system_prompt=(
                "Ты вежливый бот клиентской поддержки веб-студии. Помогаешь клиентам "
                "выбрать сайт или чат-бота, уточняешь задачи и сроки."
            ),
            quick_prompts=[
                "Сколько стоит разработка сайта?",
                "Какие сроки создания чат-бота?",
            ],
            messages=[
                {
                    "id": uuid.uuid4().hex,
                    "sender": "in",
                    "text": "Здравствуйте! Расскажите, какой проект или бот вам нужен — помогу сориентироваться.",
                    "time": t,
                    "read": True,
                }
            ],
        ),
        ChatRoom(
            id="saved-notes",
            name="Избранное",
            avatar_text="★",
            color="#d69e2e",
            is_bot=False,
            status="личные заметки",
            messages=[
                {
                    "id": uuid.uuid4().hex,
                    "sender": "out",
                    "text": "Здесь можно сохранять ссылки, промпты и заметки без ответов бота.",
                    "time": t,
                    "read": True,
                }
            ],
        ),
    ]


def main(page: ft.Page) -> None:
    page.title = "PulseChat — Flet AI Messenger"
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.DARK

    theme_name = "dark"
    ai_config = AIConfig.from_env()
    env_has_gemini = bool(ai_config.gemini_api_key)
    env_has_openai = bool(ai_config.openai_api_key)

    chats: list[ChatRoom] = create_default_chats()
    active_chat_id: str = chats[0].id
    filter_mode: str = "all"  # "all" | "bots" | "personal"
    search_query: str = ""
    typing_chat_id: str | None = None
    reply_target: dict[str, str] | None = None
    mobile_show_chat: bool = False

    def colors() -> dict[str, str]:
        return THEMES[theme_name]

    def get_active_chat() -> ChatRoom:
        for chat in chats:
            if chat.id == active_chat_id:
                return chat
        return chats[0]

    def is_mobile() -> bool:
        w = page.width or 1024
        return w < 760

    def show_snack(text: str) -> None:
        page.snack_bar = ft.SnackBar(ft.Text(text))
        page.snack_bar.open = True
        page.update()

    # UI Containers (rebuilt on state updates)
    sidebar_list = ft.ListView(expand=True, spacing=0, padding=0)
    messages_list = ft.ListView(expand=True, spacing=8, padding=ft.Padding.symmetric(vertical=14, horizontal=16), auto_scroll=True)
    quick_prompts_row = ft.Row(wrap=True, spacing=6, run_spacing=6)

    search_field = ft.TextField(
        hint_text="Поиск чата...",
        border=ft.InputBorder.NONE,
        dense=True,
        text_size=13.5,
        expand=True,
    )

    msg_input = ft.TextField(
        hint_text="Введите сообщение...",
        border=ft.InputBorder.NONE,
        multiline=True,
        min_lines=1,
        max_lines=4,
        shift_enter=True,
        expand=True,
        text_size=14.5,
    )

    reply_author_txt = ft.Text("", size=12, weight=ft.FontWeight.W_600)
    reply_preview_txt = ft.Text("", size=12.5, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    reply_bar = ft.Container(visible=False)

    # Header dynamic refs
    active_avatar_txt = ft.Text("", color="#ffffff", weight=ft.FontWeight.BOLD, size=14)
    active_avatar_circle = ft.Container(
        width=40,
        height=40,
        border_radius=20,
        alignment=ft.Alignment.CENTER,
        content=active_avatar_txt,
    )
    active_title_txt = ft.Text("", size=15.5, weight=ft.FontWeight.W_600)
    active_bot_badge = ft.Container(
        content=ft.Text("AI", size=10, weight=ft.FontWeight.BOLD, color="#00a884"),
        padding=ft.Padding.symmetric(vertical=2, horizontal=6),
        border_radius=4,
        bgcolor="#1a00a884",
    )
    active_status_txt = ft.Text("", size=12)

    ai_status_label = ft.Text("", size=11.5)

    back_btn = ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="К списку чатов", visible=False)
    theme_btn = ft.IconButton(icon=ft.Icons.LIGHT_MODE, tooltip="Сменить тему")
    new_chat_btn = ft.IconButton(icon=ft.Icons.ADD_COMMENT_OUTLINED, tooltip="Новый ИИ-чат")
    settings_btn = ft.IconButton(icon=ft.Icons.SETTINGS_OUTLINED, tooltip="Настройки ИИ")
    clear_chat_btn = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="Очистить историю")
    send_btn = ft.IconButton(
        icon=ft.Icons.SEND_ROUNDED,
        icon_color="#ffffff",
        bgcolor="#00a884",
        tooltip="Отправить",
    )

    filter_row = ft.Row(spacing=6)

    def clear_reply(_=None) -> None:
        nonlocal reply_target
        reply_target = None
        reply_bar.visible = False
        page.update()

    def set_reply(msg: dict[str, Any]) -> None:
        nonlocal reply_target
        chat = get_active_chat()
        author = "Вы" if msg["sender"] == "out" else chat.name
        reply_target = {"author": author, "text": msg["text"]}
        reply_author_txt.value = author
        reply_preview_txt.value = msg["text"]
        reply_bar.visible = True
        page.update()

    def render_filters() -> None:
        c = colors()
        items = [("all", "Все"), ("bots", "ИИ-боты"), ("personal", "Личные")]
        filter_row.controls.clear()
        for key, label in items:
            selected = filter_mode == key
            filter_row.controls.append(
                ft.Container(
                    content=ft.Text(
                        label,
                        size=12.5,
                        weight=ft.FontWeight.W_500,
                        color=c["accent"] if selected else c["text_secondary"],
                    ),
                    bgcolor="#2600a884" if selected else c["bg_header"],
                    padding=ft.Padding.symmetric(vertical=5, horizontal=12),
                    border_radius=999,
                    on_click=lambda e, k=key: on_filter_change(k),
                )
            )

    def on_filter_change(key: str) -> None:
        nonlocal filter_mode
        filter_mode = key
        render_filters()
        render_sidebar()
        page.update()

    def select_chat(chat_id: str) -> None:
        nonlocal active_chat_id, mobile_show_chat
        active_chat_id = chat_id
        chat = get_active_chat()
        chat.unread = 0
        mobile_show_chat = True
        clear_reply()
        render_all()

    def render_sidebar() -> None:
        c = colors()
        q = search_query.strip().lower()
        sidebar_list.controls.clear()

        filtered = []
        for chat in chats:
            if filter_mode == "bots" and not chat.is_bot:
                continue
            if filter_mode == "personal" and chat.is_bot:
                continue
            if q:
                in_name = q in chat.name.lower()
                in_msg = any(q in (m.get("text") or "").lower() for m in chat.messages)
                if not (in_name or in_msg):
                    continue
            filtered.append(chat)

        if not filtered:
            sidebar_list.controls.append(
                ft.Container(
                    padding=24,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text("Чаты не найдены", color=c["text_secondary"], size=13.5),
                )
            )
            return

        for chat in filtered:
            last = chat.messages[-1] if chat.messages else None
            is_typing = typing_chat_id == chat.id
            if is_typing:
                preview = "печатает..."
            elif last:
                prefix = "Вы: " if last["sender"] == "out" else ""
                preview = prefix + last["text"].replace("\n", " ")
            else:
                preview = "Нет сообщений"
            last_time = last["time"] if last else ""
            is_active = chat.id == active_chat_id

            badge = (
                ft.Container(
                    content=ft.Text(str(chat.unread), size=11, weight=ft.FontWeight.BOLD, color=c["badge_text"]),
                    bgcolor=c["accent"],
                    padding=ft.Padding.symmetric(vertical=2, horizontal=7),
                    border_radius=999,
                )
                if chat.unread > 0
                else ft.Container()
            )

            sidebar_list.controls.append(
                ft.Container(
                    bgcolor=c["bg_active"] if is_active else None,
                    padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                    border=ft.Border.only(bottom=ft.BorderSide(1, c["border"])),
                    on_click=lambda e, cid=chat.id: select_chat(cid),
                    content=ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=44,
                                height=44,
                                border_radius=22,
                                bgcolor=chat.color,
                                alignment=ft.Alignment.CENTER,
                                content=ft.Text(chat.avatar_text, color="#ffffff", weight=ft.FontWeight.BOLD, size=15),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Row(
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                        controls=[
                                            ft.Row(
                                                spacing=6,
                                                controls=[
                                                    ft.Text(
                                                        chat.name,
                                                        size=14.5,
                                                        weight=ft.FontWeight.W_600,
                                                        color=c["text_primary"],
                                                        max_lines=1,
                                                        overflow=ft.TextOverflow.ELLIPSIS,
                                                    ),
                                                    *(
                                                        [
                                                            ft.Container(
                                                                content=ft.Text("AI", size=9.5, weight=ft.FontWeight.BOLD, color=c["accent"]),
                                                                bgcolor="#1f00a884",
                                                                padding=ft.Padding.symmetric(vertical=1, horizontal=5),
                                                                border_radius=4,
                                                            )
                                                        ]
                                                        if chat.is_bot
                                                        else []
                                                    ),
                                                ],
                                            ),
                                            ft.Text(last_time, size=11.5, color=c["text_secondary"]),
                                        ],
                                    ),
                                    ft.Row(
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                        controls=[
                                            ft.Text(
                                                preview,
                                                size=12.8,
                                                color=c["accent"] if is_typing else c["text_secondary"],
                                                max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                                expand=True,
                                            ),
                                            badge,
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                )
            )

    def render_header() -> None:
        c = colors()
        chat = get_active_chat()
        active_avatar_txt.value = chat.avatar_text
        active_avatar_circle.bgcolor = chat.color
        active_title_txt.value = chat.name
        active_title_txt.color = c["text_primary"]
        active_bot_badge.visible = chat.is_bot

        provider = ai_config.resolved_provider()
        if typing_chat_id == chat.id:
            active_status_txt.value = "печатает..."
            active_status_txt.color = c["accent"]
        elif chat.is_bot:
            if provider == "gemini":
                active_status_txt.value = f"в сети · Gemini ({ai_config.gemini_model})"
            elif provider == "openai":
                active_status_txt.value = f"в сети · {ai_config.openai_model}"
            else:
                active_status_txt.value = "в сети · демо-режим (добавьте API-ключ)"
            active_status_txt.color = c["accent"]
        else:
            active_status_txt.value = chat.status
            active_status_txt.color = c["text_secondary"]

        if provider == "gemini":
            ai_status_label.value = "ИИ: Gemini"
            ai_status_label.color = c["accent"]
        elif provider == "openai":
            ai_status_label.value = "ИИ: OpenAI API"
            ai_status_label.color = c["accent"]
        else:
            ai_status_label.value = "ИИ: демо (без ключа)"
            ai_status_label.color = c["text_secondary"]

    async def copy_message_text(text: str) -> None:
        try:
            await ft.Clipboard().set(text)
            show_snack("Скопировано в буфер обмена")
        except Exception:
            show_snack("Не удалось скопировать")

    def delete_message(msg_id: str) -> None:
        chat = get_active_chat()
        chat.messages = [m for m in chat.messages if m["id"] != msg_id]
        render_all()

    def render_messages() -> None:
        c = colors()
        chat = get_active_chat()
        messages_list.controls.clear()

        messages_list.controls.append(
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        content=ft.Text("Сегодня", size=11.5, color=c["text_secondary"]),
                        bgcolor=c["bg_header"],
                        padding=ft.Padding.symmetric(vertical=4, horizontal=12),
                        border_radius=8,
                    )
                ],
            )
        )

        for msg in chat.messages:
            is_out = msg["sender"] == "out"
            bubble_bg = c["bubble_out"] if is_out else c["bubble_in"]
            radius = (
                ft.BorderRadius.only(top_left=12, top_right=2, bottom_left=12, bottom_right=12)
                if is_out
                else ft.BorderRadius.only(top_left=2, top_right=12, bottom_left=12, bottom_right=12)
            )

            inner_controls: list[ft.Control] = []

            if msg.get("reply_to"):
                rt = msg["reply_to"]
                inner_controls.append(
                    ft.Container(
                        bgcolor="#22000000" if theme_name == "dark" else "#12000000",
                        border=ft.Border.only(left=ft.BorderSide(3, c["accent"])),
                        border_radius=6,
                        padding=ft.Padding.symmetric(vertical=4, horizontal=8),
                        content=ft.Column(
                            spacing=1,
                            controls=[
                                ft.Text(rt["author"], size=11.5, weight=ft.FontWeight.W_600, color=c["accent"]),
                                ft.Text(rt["text"], size=12, color=c["text_secondary"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ],
                        ),
                    )
                )

            inner_controls.append(
                ft.Text(
                    msg["text"],
                    size=14.2,
                    color=c["text_primary"],
                    selectable=True,
                )
            )

            meta_items: list[ft.Control] = [
                ft.Text(msg["time"], size=11, color=c["text_secondary"]),
            ]
            if is_out:
                meta_items.append(
                    ft.Icon(
                        icon=ft.Icons.DONE_ALL,
                        size=15,
                        color=c["check_read"] if msg.get("read") else c["text_secondary"],
                    )
                )

            action_menu = ft.PopupMenuButton(
                icon=ft.Icons.MORE_HORIZ,
                icon_size=15,
                icon_color=c["text_secondary"],
                tooltip="Действия",
                items=[
                    ft.PopupMenuItem(content="Ответить", on_click=lambda e, m=msg: set_reply(m)),
                    ft.PopupMenuItem(content="Копировать", on_click=lambda e, txt=msg["text"]: page.run_task(copy_message_text, txt)),
                    ft.PopupMenuItem(content="Удалить", on_click=lambda e, mid=msg["id"]: delete_message(mid)),
                ],
            )

            inner_controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    spacing=4,
                    controls=[action_menu, *meta_items],
                )
            )

            bubble = ft.Container(
                bgcolor=bubble_bg,
                border_radius=radius,
                padding=ft.Padding.only(left=12, right=10, top=8, bottom=4),
                width=min(520, int((page.width or 960) * 0.72)),
                content=ft.Column(spacing=4, tight=True, controls=inner_controls),
            )

            messages_list.controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.END if is_out else ft.MainAxisAlignment.START,
                    controls=[bubble],
                )
            )

        if typing_chat_id == chat.id:
            messages_list.controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.START,
                    controls=[
                        ft.Container(
                            bgcolor=c["bubble_in"],
                            border_radius=12,
                            padding=ft.Padding.symmetric(vertical=8, horizontal=12),
                            content=ft.Row(
                                spacing=8,
                                tight=True,
                                controls=[
                                    ft.ProgressRing(width=14, height=14, stroke_width=2, color=c["accent"]),
                                    ft.Text("ИИ печатает...", size=13, color=c["text_secondary"]),
                                ],
                            ),
                        )
                    ],
                )
            )

        # Quick prompts under chat when bot chat has prompts
        quick_prompts_row.controls.clear()
        if chat.is_bot and chat.quick_prompts and typing_chat_id != chat.id:
            for prompt in chat.quick_prompts:
                quick_prompts_row.controls.append(
                    ft.Container(
                        content=ft.Text(prompt, size=12.5, color=c["accent"]),
                        bgcolor=c["bg_header"],
                        border=ft.Border.all(1, c["border"]),
                        border_radius=999,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=11),
                        on_click=lambda e, p=prompt: page.run_task(send_message_async, p),
                    )
                )

    async def send_message_async(custom_text: str | None = None) -> None:
        nonlocal typing_chat_id
        chat = get_active_chat()
        text = (custom_text if custom_text is not None else (msg_input.value or "")).strip()
        if not text:
            return

        if custom_text is None:
            msg_input.value = ""

        out_msg: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "sender": "out",
            "text": text,
            "time": now_hhmm(),
            "read": not chat.is_bot,
        }
        if reply_target:
            out_msg["reply_to"] = dict(reply_target)
            clear_reply()

        chat.messages.append(out_msg)
        render_all()

        if not chat.is_bot:
            return

        typing_chat_id = chat.id
        render_all()

        reply_text, _source = await generate_ai_reply(
            config=ai_config,
            system_prompt=chat.system_prompt or f"Ты полезный ИИ-ассистент {chat.name}.",
            history=chat.messages,
            user_text=text,
        )

        typing_chat_id = None
        for m in chat.messages:
            if m["sender"] == "out":
                m["read"] = True

        chat.messages.append(
            {
                "id": uuid.uuid4().hex,
                "sender": "in",
                "text": reply_text,
                "time": now_hhmm(),
                "read": active_chat_id == chat.id,
            }
        )
        if active_chat_id != chat.id:
            chat.unread += 1

        render_all()

    # Dialogs
    def open_new_chat_dialog(_=None) -> None:
        name_tf = ft.TextField(label="Имя бота или название чата", hint_text="Например: Маркетолог ИИ")
        is_bot_sw = ft.Switch(label="Это ИИ-чат-бот", value=True)
        prompt_tf = ft.TextField(
            label="Системный промпт (роль ИИ)",
            multiline=True,
            min_lines=2,
            max_lines=4,
            value="Ты полезный ИИ-ассистент. Отвечай кратко и по делу на русском языке.",
        )

        def create_chat(_e) -> None:
            nonlocal active_chat_id, mobile_show_chat
            name = (name_tf.value or "").strip()
            if not name:
                show_snack("Введите название чата")
                return
            palette = ["#00a884", "#2b6cb0", "#805ad5", "#dd6b20", "#d53f8c", "#319795"]
            is_bot = bool(is_bot_sw.value)
            new_room = ChatRoom(
                id="chat_" + uuid.uuid4().hex[:8],
                name=name,
                avatar_text=name[:2].upper(),
                color=palette[len(chats) % len(palette)],
                is_bot=is_bot,
                status="в сети · свой ИИ-бот" if is_bot else "личные заметки",
                system_prompt=(prompt_tf.value or "").strip(),
                messages=(
                    [
                        {
                            "id": uuid.uuid4().hex,
                            "sender": "in",
                            "text": f"Привет! Я {name}. Чем могу помочь?",
                            "time": now_hhmm(),
                            "read": True,
                        }
                    ]
                    if is_bot
                    else []
                ),
            )
            chats.insert(0, new_room)
            active_chat_id = new_room.id
            mobile_show_chat = True
            page.pop_dialog()
            render_all()
            show_snack(f"Чат «{name}» создан")

        dlg = ft.AlertDialog(
            title=ft.Text("Новый чат / ИИ-бот"),
            content=ft.Container(
                width=380,
                content=ft.Column(tight=True, spacing=10, controls=[name_tf, is_bot_sw, prompt_tf]),
            ),
            actions=[
                ft.TextButton(content="Отмена", on_click=lambda _: page.pop_dialog()),
                ft.Button(content="Создать", on_click=create_chat),
            ],
        )
        page.show_dialog(dlg)

    def open_settings_dialog(_=None) -> None:
        provider_dd = ft.Dropdown(
            label="Провайдер ИИ",
            value=ai_config.provider,
            options=[
                ft.dropdown.Option("auto", "Авто (Gemini, затем OpenAI)"),
                ft.dropdown.Option("gemini", "Google Gemini API"),
                ft.dropdown.Option("openai", "OpenAI-совместимый API"),
            ],
        )
        gemini_key_tf = ft.TextField(
            label="GEMINI_API_KEY (Google AI Studio)",
            password=True,
            can_reveal_password=True,
            value="" if env_has_gemini else ai_config.gemini_api_key,
            hint_text="Задан через переменную окружения" if env_has_gemini else "AIza...",
        )
        gemini_model_tf = ft.TextField(
            label="Модель Gemini",
            value=ai_config.gemini_model or DEFAULT_GEMINI_MODEL,
        )
        openai_url_tf = ft.TextField(
            label="OpenAI-совместимый Base URL",
            value=ai_config.openai_base_url or DEFAULT_OPENAI_BASE_URL,
            hint_text="https://openrouter.ai/api/v1 или https://api.groq.com/openai/v1",
        )
        openai_key_tf = ft.TextField(
            label="AI_API_KEY",
            password=True,
            can_reveal_password=True,
            value="" if env_has_openai else ai_config.openai_api_key,
            hint_text="Задан через переменную окружения" if env_has_openai else "sk-...",
        )
        openai_model_tf = ft.TextField(
            label="Модель (OpenAI / Groq / OpenRouter)",
            value=ai_config.openai_model or DEFAULT_OPENAI_MODEL,
        )

        def save_settings(_e) -> None:
            ai_config.provider = provider_dd.value or "auto"
            if (gemini_key_tf.value or "").strip():
                ai_config.gemini_api_key = gemini_key_tf.value.strip()
            ai_config.gemini_model = (gemini_model_tf.value or DEFAULT_GEMINI_MODEL).strip()
            ai_config.openai_base_url = (openai_url_tf.value or DEFAULT_OPENAI_BASE_URL).strip()
            if (openai_key_tf.value or "").strip():
                ai_config.openai_api_key = openai_key_tf.value.strip()
            ai_config.openai_model = (openai_model_tf.value or DEFAULT_OPENAI_MODEL).strip()
            page.pop_dialog()
            render_all()
            show_snack("Настройки ИИ сохранены")

        dlg = ft.AlertDialog(
            title=ft.Text("Настройки ИИ"),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=10,
                    controls=[
                        provider_dd,
                        gemini_key_tf,
                        gemini_model_tf,
                        ft.Divider(height=8),
                        openai_url_tf,
                        openai_key_tf,
                        openai_model_tf,
                    ],
                ),
            ),
            actions=[
                ft.TextButton(content="Отмена", on_click=lambda _: page.pop_dialog()),
                ft.Button(content="Сохранить", on_click=save_settings),
            ],
        )
        page.show_dialog(dlg)

    def clear_active_chat(_=None) -> None:
        chat = get_active_chat()
        chat.messages.clear()
        render_all()
        show_snack("История чата очищена")

    def toggle_theme(_=None) -> None:
        nonlocal theme_name
        theme_name = "light" if theme_name == "dark" else "dark"
        page.theme_mode = ft.ThemeMode.LIGHT if theme_name == "light" else ft.ThemeMode.DARK
        theme_btn.icon = ft.Icons.DARK_MODE if theme_name == "light" else ft.Icons.LIGHT_MODE
        render_all()

    def on_search_change(e) -> None:
        nonlocal search_query
        search_query = e.control.value or ""
        render_sidebar()
        page.update()

    def on_mobile_back(_=None) -> None:
        nonlocal mobile_show_chat
        mobile_show_chat = False
        apply_layout()
        page.update()

    # Wire handlers
    search_field.on_change = on_search_change
    msg_input.on_submit = lambda e: page.run_task(send_message_async)
    send_btn.on_click = lambda e: page.run_task(send_message_async)
    theme_btn.on_click = toggle_theme
    new_chat_btn.on_click = open_new_chat_dialog
    settings_btn.on_click = open_settings_dialog
    clear_chat_btn.on_click = clear_active_chat
    back_btn.on_click = on_mobile_back

    # Static structural shells
    sidebar_header = ft.Container(height=60, padding=ft.Padding.symmetric(horizontal=12))
    search_wrap = ft.Container(padding=ft.Padding.only(left=12, right=12, top=8, bottom=8))
    sidebar_panel = ft.Container(width=340)

    chat_header = ft.Container(height=60, padding=ft.Padding.symmetric(horizontal=12))
    quick_bar = ft.Container(padding=ft.Padding.symmetric(vertical=4, horizontal=16), content=quick_prompts_row)
    composer_box = ft.Container(border_radius=12, padding=ft.Padding.symmetric(vertical=2, horizontal=12), expand=True, content=msg_input)
    composer_bar = ft.Container(padding=ft.Padding.symmetric(vertical=8, horizontal=12))
    chat_panel = ft.Container(expand=True)

    root_row = ft.Row(expand=True, spacing=0, controls=[sidebar_panel, chat_panel])

    def apply_layout() -> None:
        c = colors()
        page.bgcolor = c["bg_app"]

        sidebar_header.bgcolor = c["bg_header"]
        sidebar_header.content = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.Container(
                            width=36,
                            height=36,
                            border_radius=18,
                            bgcolor=c["accent"],
                            alignment=ft.Alignment.CENTER,
                            content=ft.Text("P", color="#ffffff", weight=ft.FontWeight.BOLD),
                        ),
                        ft.Column(
                            spacing=0,
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[
                                ft.Text("PulseChat", size=15, weight=ft.FontWeight.BOLD, color=c["text_primary"]),
                                ai_status_label,
                            ],
                        ),
                    ],
                ),
                ft.Row(spacing=0, controls=[new_chat_btn, theme_btn, settings_btn]),
            ],
        )

        search_wrap.border = ft.Border.only(bottom=ft.BorderSide(1, c["border"]))
        search_wrap.content = ft.Column(
            spacing=8,
            controls=[
                ft.Container(
                    bgcolor=c["bg_header"],
                    border_radius=10,
                    padding=ft.Padding.symmetric(vertical=2, horizontal=10),
                    content=ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(icon=ft.Icons.SEARCH, size=18, color=c["text_secondary"]),
                            search_field,
                        ],
                    ),
                ),
                filter_row,
            ],
        )

        sidebar_panel.bgcolor = c["bg_sidebar"]
        sidebar_panel.border = ft.Border.only(right=ft.BorderSide(1, c["border"]))
        sidebar_panel.content = ft.Column(
            expand=True,
            spacing=0,
            controls=[sidebar_header, search_wrap, sidebar_list],
        )

        chat_header.bgcolor = c["bg_header"]
        chat_header.border = ft.Border.only(bottom=ft.BorderSide(1, c["border"]))
        chat_header.content = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Row(
                    spacing=10,
                    expand=True,
                    controls=[
                        back_btn,
                        active_avatar_circle,
                        ft.Column(
                            spacing=1,
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[
                                ft.Row(spacing=6, controls=[active_title_txt, active_bot_badge]),
                                active_status_txt,
                            ],
                        ),
                    ],
                ),
                clear_chat_btn,
            ],
        )

        reply_bar.bgcolor = c["bg_header"]
        reply_bar.border = ft.Border.only(top=ft.BorderSide(1, c["border"]))
        reply_bar.padding = ft.Padding.symmetric(vertical=6, horizontal=14)
        reply_author_txt.color = c["accent"]
        reply_preview_txt.color = c["text_secondary"]
        reply_bar.content = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Container(
                    expand=True,
                    border=ft.Border.only(left=ft.BorderSide(3, c["accent"])),
                    padding=ft.Padding.only(left=8),
                    content=ft.Column(spacing=1, controls=[reply_author_txt, reply_preview_txt]),
                ),
                ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, on_click=clear_reply),
            ],
        )

        composer_box.bgcolor = c["bg_input"]
        composer_bar.bgcolor = c["bg_header"]
        composer_bar.border = ft.Border.only(top=ft.BorderSide(1, c["border"]))
        composer_bar.content = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.END,
            controls=[composer_box, send_btn],
        )

        chat_panel.bgcolor = c["bg_app"]
        chat_panel.content = ft.Column(
            expand=True,
            spacing=0,
            controls=[
                chat_header,
                messages_list,
                quick_bar,
                reply_bar,
                composer_bar,
            ],
        )

        # Responsive toggle
        mobile = is_mobile()
        back_btn.visible = mobile
        if mobile:
            sidebar_panel.width = None
            sidebar_panel.expand = not mobile_show_chat
            sidebar_panel.visible = not mobile_show_chat
            chat_panel.visible = mobile_show_chat
            chat_panel.expand = mobile_show_chat
        else:
            sidebar_panel.width = 340
            sidebar_panel.expand = False
            sidebar_panel.visible = True
            chat_panel.visible = True
            chat_panel.expand = True

    def render_all() -> None:
        render_filters()
        render_header()
        render_sidebar()
        render_messages()
        apply_layout()
        page.update()

    def on_resize(_e) -> None:
        apply_layout()
        render_messages()
        page.update()

    page.on_resize = on_resize
    page.add(root_row)
    render_all()


if __name__ == "__main__":
    if os.getenv("PORT") or os.getenv("FLET_FORCE_WEB_SERVER"):
        port = int(os.getenv("PORT", os.getenv("FLET_SERVER_PORT", "8000")))
        ft.run(main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=port)
    else:
        ft.run(main)
else:
    app = ft.run(main, export_asgi_app=True)
