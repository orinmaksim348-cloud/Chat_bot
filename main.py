"""PulseChat — живой WhatsApp-мессенджер на Flet 1.0 для общения посетителей сайта + бот с заготовками."""

from __future__ import annotations

import datetime
import os
import threading
import uuid
from typing import Any

import flet as ft

from bot_engine import QUICK_BUTTONS, get_bot_reply


THEMES = {
    "dark": {
        "bg_app": "#0b141a",
        "bg_sidebar": "#111b21",
        "bg_header": "#202c33",
        "bg_input": "#2a3942",
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

AVATAR_COLORS = [
    "#00a884",
    "#2b6cb0",
    "#805ad5",
    "#dd6b20",
    "#d53f8c",
    "#319795",
    "#c53030",
    "#38a169",
]

# Общее серверное состояние (разделяется между всеми подключёнными пользователями)
STATE_LOCK = threading.Lock()
ONLINE_USERS: dict[str, dict[str, str]] = {}  # user_id -> {"id", "name", "color"}
ROOMS_HISTORY: dict[str, list[dict[str, Any]]] = {
    "general": [
        {
            "id": "welcome_general",
            "room_id": "general",
            "kind": "system",
            "text": "Добро пожаловать в Общий чат! Здесь общаются все, кто сейчас на сайте.",
            "time": datetime.datetime.now().strftime("%H:%M"),
        }
    ]
}
MAX_HISTORY_PER_ROOM = 200


def now_hhmm() -> str:
    return datetime.datetime.now().strftime("%H:%M")


def dm_room_id(uid1: str, uid2: str) -> str:
    a, b = sorted([uid1, uid2])
    return f"dm:{a}:{b}"


def append_room_message(room_id: str, msg: dict[str, Any]) -> None:
    with STATE_LOCK:
        buf = ROOMS_HISTORY.setdefault(room_id, [])
        buf.append(msg)
        if len(buf) > MAX_HISTORY_PER_ROOM:
            del buf[:-MAX_HISTORY_PER_ROOM]


def get_room_history(room_id: str) -> list[dict[str, Any]]:
    with STATE_LOCK:
        return list(ROOMS_HISTORY.get(room_id, []))


def get_online_snapshot() -> list[dict[str, str]]:
    with STATE_LOCK:
        return list(ONLINE_USERS.values())


def main(page: ft.Page) -> None:
    page.title = "PulseChat — Живой мессенджер"
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.DARK

    theme_name = "dark"
    user_id = "u_" + uuid.uuid4().hex[:10]
    user_name = ""
    user_color = AVATAR_COLORS[hash(user_id) % len(AVATAR_COLORS)]
    joined = False

    active_room_id = "general"  # "general" | "bot" | "saved" | "dm:..."
    filter_mode = "all"  # "all" | "people" | "bot"
    search_query = ""
    mobile_show_chat = False
    reply_target: dict[str, str] | None = None
    unread_counts: dict[str, int] = {}

    # Личная история бота и избранного для текущей сессии
    bot_messages: list[dict[str, Any]] = [
        {
            "id": uuid.uuid4().hex,
            "sender_id": "bot",
            "sender_name": "Бот-Помощник",
            "sender_color": "#00a884",
            "text": (
                "Привет! Я Бот-Помощник с заготовленными ответами.\n"
                "Нажми кнопку ниже или напиши «Помощь»."
            ),
            "time": now_hhmm(),
        }
    ]
    bot_quick_buttons: list[str] = list(QUICK_BUTTONS)

    saved_messages: list[dict[str, Any]] = [
        {
            "id": uuid.uuid4().hex,
            "sender_id": user_id,
            "sender_name": "Вы",
            "sender_color": user_color,
            "text": "Здесь можно сохранять личные заметки и ссылки — их видите только вы.",
            "time": now_hhmm(),
        }
    ]

    # Кеш известных собеседников (чтобы личный чат не пропадал, если человек вышел)
    known_peers: dict[str, dict[str, str]] = {}

    def colors() -> dict[str, str]:
        return THEMES[theme_name]

    def is_mobile() -> bool:
        return (page.width or 1024) < 760

    def show_snack(text: str) -> None:
        page.snack_bar = ft.SnackBar(ft.Text(text))
        page.snack_bar.open = True
        page.update()

    # Основные контролы
    sidebar_list = ft.ListView(expand=True, spacing=0, padding=0)
    messages_list = ft.ListView(
        expand=True,
        spacing=8,
        padding=ft.Padding.symmetric(vertical=14, horizontal=16),
        auto_scroll=True,
    )
    quick_buttons_row = ft.Row(wrap=True, spacing=6, run_spacing=6)
    filter_row = ft.Row(spacing=6)

    search_field = ft.TextField(
        hint_text="Поиск чата или человека...",
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

    # Шапка активного чата
    active_avatar_txt = ft.Text("", color="#ffffff", weight=ft.FontWeight.BOLD, size=14)
    active_avatar_circle = ft.Container(
        width=40,
        height=40,
        border_radius=20,
        alignment=ft.Alignment.CENTER,
        content=active_avatar_txt,
    )
    active_title_txt = ft.Text("", size=15.5, weight=ft.FontWeight.W_600)
    active_badge = ft.Container(
        content=ft.Text("BOT", size=10, weight=ft.FontWeight.BOLD, color="#00a884"),
        padding=ft.Padding.symmetric(vertical=2, horizontal=6),
        border_radius=4,
        bgcolor="#1a00a884",
        visible=False,
    )
    active_status_txt = ft.Text("", size=12)

    me_avatar_txt = ft.Text("?", color="#ffffff", weight=ft.FontWeight.BOLD, size=14)
    me_avatar_circle = ft.Container(
        width=36,
        height=36,
        border_radius=18,
        alignment=ft.Alignment.CENTER,
        content=me_avatar_txt,
    )
    me_name_txt = ft.Text("PulseChat", size=15, weight=ft.FontWeight.BOLD)
    online_counter_txt = ft.Text("Онлайн: 0", size=11.5)

    back_btn = ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="К списку чатов", visible=False)
    theme_btn = ft.IconButton(icon=ft.Icons.LIGHT_MODE, tooltip="Сменить тему")
    profile_btn = ft.IconButton(icon=ft.Icons.PERSON_OUTLINE, tooltip="Изменить имя")
    send_btn = ft.IconButton(
        icon=ft.Icons.SEND_ROUNDED,
        icon_color="#ffffff",
        bgcolor="#00a884",
        tooltip="Отправить",
    )

    def clear_reply(_=None) -> None:
        nonlocal reply_target
        reply_target = None
        reply_bar.visible = False
        page.update()

    def set_reply(msg: dict[str, Any]) -> None:
        nonlocal reply_target
        author = "Вы" if msg.get("sender_id") == user_id else msg.get("sender_name", "Участник")
        reply_target = {"author": author, "text": msg.get("text", "")}
        reply_author_txt.value = author
        reply_preview_txt.value = msg.get("text", "")
        reply_bar.visible = True
        page.update()

    def peer_from_dm_room(room_id: str) -> dict[str, str] | None:
        if not room_id.startswith("dm:"):
            return None
        parts = room_id.split(":")
        if len(parts) != 3:
            return None
        other_id = parts[2] if parts[1] == user_id else parts[1]
        with STATE_LOCK:
            if other_id in ONLINE_USERS:
                return dict(ONLINE_USERS[other_id])
        return known_peers.get(other_id)

    def select_room(room_id: str) -> None:
        nonlocal active_room_id, mobile_show_chat
        active_room_id = room_id
        unread_counts[room_id] = 0
        mobile_show_chat = True
        clear_reply()
        render_all()

    def render_filters() -> None:
        c = colors()
        items = [("all", "Все"), ("people", "Люди онлайн"), ("bot", "Бот")]
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

    def build_sidebar_item(
        room_id: str,
        title: str,
        avatar_text: str,
        avatar_color: str,
        preview: str,
        time_str: str,
        unread: int = 0,
        tag: str = "",
        is_online: bool = False,
    ) -> ft.Container:
        c = colors()
        is_active = room_id == active_room_id

        avatar_stack = ft.Stack(
            width=44,
            height=44,
            controls=[
                ft.Container(
                    width=44,
                    height=44,
                    border_radius=22,
                    bgcolor=avatar_color,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(avatar_text, color="#ffffff", weight=ft.FontWeight.BOLD, size=15),
                ),
                *(
                    [
                        ft.Container(
                            width=12,
                            height=12,
                            border_radius=6,
                            bgcolor="#25d366",
                            border=ft.Border.all(2, c["bg_sidebar"]),
                            right=0,
                            bottom=0,
                        )
                    ]
                    if is_online
                    else []
                ),
            ],
        )

        badge = (
            ft.Container(
                content=ft.Text(str(unread), size=11, weight=ft.FontWeight.BOLD, color=c["badge_text"]),
                bgcolor=c["accent"],
                padding=ft.Padding.symmetric(vertical=2, horizontal=7),
                border_radius=999,
            )
            if unread > 0
            else ft.Container()
        )

        return ft.Container(
            bgcolor=c["bg_active"] if is_active else None,
            padding=ft.Padding.symmetric(vertical=10, horizontal=12),
            border=ft.Border.only(bottom=ft.BorderSide(1, c["border"])),
            on_click=lambda e, rid=room_id: select_room(rid),
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    avatar_stack,
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
                                                title,
                                                size=14.5,
                                                weight=ft.FontWeight.W_600,
                                                color=c["text_primary"],
                                                max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            ),
                                            *(
                                                [
                                                    ft.Container(
                                                        content=ft.Text(tag, size=9.5, weight=ft.FontWeight.BOLD, color=c["accent"]),
                                                        bgcolor="#1f00a884",
                                                        padding=ft.Padding.symmetric(vertical=1, horizontal=5),
                                                        border_radius=4,
                                                    )
                                                ]
                                                if tag
                                                else []
                                            ),
                                        ],
                                    ),
                                    ft.Text(time_str, size=11.5, color=c["text_secondary"]),
                                ],
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text(
                                        preview,
                                        size=12.8,
                                        color=c["text_secondary"],
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

    def render_sidebar() -> None:
        c = colors()
        q = search_query.strip().lower()
        online_all = get_online_snapshot()
        other_users = [u for u in online_all if u["id"] != user_id]
        for u in other_users:
            known_peers[u["id"]] = u

        online_counter_txt.value = f"Онлайн на сайте: {len(online_all)}"
        online_counter_txt.color = c["accent"]

        sidebar_list.controls.clear()

        # 1. Общий чат
        if filter_mode in {"all", "people"}:
            gen_hist = get_room_history("general")
            last_gen = gen_hist[-1] if gen_hist else None
            gen_preview = last_gen["text"].replace("\n", " ") if last_gen else "Напишите первым!"
            if last_gen and last_gen.get("kind") != "system":
                who = "Вы" if last_gen.get("sender_id") == user_id else last_gen.get("sender_name", "")
                gen_preview = f"{who}: {gen_preview}"
            if not q or q in "общий чат" or q in gen_preview.lower():
                sidebar_list.controls.append(
                    build_sidebar_item(
                        room_id="general",
                        title="Общий чат",
                        avatar_text="🌐",
                        avatar_color="#00a884",
                        preview=gen_preview,
                        time_str=last_gen["time"] if last_gen else "",
                        unread=unread_counts.get("general", 0),
                        tag=f"{len(online_all)} онлайн",
                    )
                )

        # 2. Бот-Помощник (с заготовленными сообщениями)
        if filter_mode in {"all", "bot"}:
            last_bot = bot_messages[-1] if bot_messages else None
            bot_preview = last_bot["text"].replace("\n", " ") if last_bot else "Напишите боту"
            if not q or q in "бот помощник" or q in bot_preview.lower():
                sidebar_list.controls.append(
                    build_sidebar_item(
                        room_id="bot",
                        title="Бот-Помощник",
                        avatar_text="🤖",
                        avatar_color="#2b6cb0",
                        preview=bot_preview,
                        time_str=last_bot["time"] if last_bot else "",
                        unread=unread_counts.get("bot", 0),
                        tag="BOT",
                        is_online=True,
                    )
                )

        # 3. Избранное
        if filter_mode == "all":
            last_saved = saved_messages[-1] if saved_messages else None
            saved_preview = last_saved["text"].replace("\n", " ") if last_saved else "Личные заметки"
            if not q or q in "избранное заметки" or q in saved_preview.lower():
                sidebar_list.controls.append(
                    build_sidebar_item(
                        room_id="saved",
                        title="Избранное",
                        avatar_text="★",
                        avatar_color="#805ad5",
                        preview=saved_preview,
                        time_str=last_saved["time"] if last_saved else "",
                    )
                )

        # 4. Люди на сайте (личные чаты 1-на-1)
        if filter_mode in {"all", "people"}:
            sidebar_list.controls.append(
                ft.Container(
                    padding=ft.Padding.only(left=14, right=14, top=12, bottom=6),
                    content=ft.Text(
                        f"ЛЮДИ НА САЙТЕ ({len(other_users)})",
                        size=11,
                        weight=ft.FontWeight.W_600,
                        color=c["text_secondary"],
                    ),
                )
            )
            if not other_users:
                sidebar_list.controls.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(vertical=10, horizontal=14),
                        content=ft.Text(
                            "Пока вы один на сайте. Откройте ссылку во второй вкладке или отправьте другу — собеседник сразу появится здесь.",
                            size=12.5,
                            color=c["text_secondary"],
                        ),
                    )
                )
            else:
                for peer in other_users:
                    rid = dm_room_id(user_id, peer["id"])
                    hist = get_room_history(rid)
                    last_m = hist[-1] if hist else None
                    prev = "Нажмите, чтобы написать в личку"
                    if last_m:
                        who = "Вы: " if last_m.get("sender_id") == user_id else ""
                        prev = who + last_m["text"].replace("\n", " ")
                    if q and q not in peer["name"].lower() and q not in prev.lower():
                        continue
                    sidebar_list.controls.append(
                        build_sidebar_item(
                            room_id=rid,
                            title=peer["name"],
                            avatar_text=peer["name"][:2].upper(),
                            avatar_color=peer["color"],
                            preview=prev,
                            time_str=last_m["time"] if last_m else "",
                            unread=unread_counts.get(rid, 0),
                            is_online=True,
                        )
                    )

    def render_header() -> None:
        c = colors()
        me_avatar_txt.value = (user_name[:1].upper() if user_name else "?")
        me_avatar_circle.bgcolor = user_color
        me_name_txt.value = user_name or "PulseChat"
        me_name_txt.color = c["text_primary"]

        online_all = get_online_snapshot()

        if active_room_id == "general":
            active_avatar_txt.value = "🌐"
            active_avatar_circle.bgcolor = "#00a884"
            active_title_txt.value = "Общий чат"
            active_badge.visible = False
            active_status_txt.value = f"участников онлайн: {len(online_all)}"
            active_status_txt.color = c["accent"]
        elif active_room_id == "bot":
            active_avatar_txt.value = "🤖"
            active_avatar_circle.bgcolor = "#2b6cb0"
            active_title_txt.value = "Бот-Помощник"
            active_badge.visible = True
            active_status_txt.value = "в сети · быстрые команды"
            active_status_txt.color = c["accent"]
        elif active_room_id == "saved":
            active_avatar_txt.value = "★"
            active_avatar_circle.bgcolor = "#805ad5"
            active_title_txt.value = "Избранное"
            active_badge.visible = False
            active_status_txt.value = "личные заметки"
            active_status_txt.color = c["text_secondary"]
        else:
            peer = peer_from_dm_room(active_room_id)
            online_ids = {u["id"] for u in online_all}
            if peer:
                active_avatar_txt.value = peer["name"][:2].upper()
                active_avatar_circle.bgcolor = peer["color"]
                active_title_txt.value = peer["name"]
                active_badge.visible = False
                if peer["id"] in online_ids:
                    active_status_txt.value = "в сети · личный чат"
                    active_status_txt.color = c["accent"]
                else:
                    active_status_txt.value = "не в сети"
                    active_status_txt.color = c["text_secondary"]
            else:
                active_avatar_txt.value = "?"
                active_avatar_circle.bgcolor = "#667781"
                active_title_txt.value = "Личный чат"
                active_badge.visible = False
                active_status_txt.value = "собеседник вышел"
                active_status_txt.color = c["text_secondary"]

        active_title_txt.color = c["text_primary"]

    async def copy_message_text(text: str) -> None:
        try:
            await ft.Clipboard().set(text)
            show_snack("Скопировано")
        except Exception:
            show_snack("Не удалось скопировать")

    def render_messages() -> None:
        c = colors()
        messages_list.controls.clear()

        if active_room_id == "bot":
            msgs = bot_messages
        elif active_room_id == "saved":
            msgs = saved_messages
        else:
            msgs = get_room_history(active_room_id)

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

        if not msgs and active_room_id.startswith("dm:"):
            messages_list.controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            content=ft.Text(
                                "Это начало личной переписки. Напишите привет!",
                                size=12.5,
                                color=c["text_secondary"],
                            ),
                            bgcolor=c["bg_header"],
                            padding=ft.Padding.symmetric(vertical=6, horizontal=14),
                            border_radius=10,
                        )
                    ],
                )
            )

        for msg in msgs:
            if msg.get("kind") == "system":
                messages_list.controls.append(
                    ft.Row(
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                content=ft.Text(msg["text"], size=12, color=c["text_secondary"]),
                                bgcolor=c["bg_header"],
                                padding=ft.Padding.symmetric(vertical=4, horizontal=12),
                                border_radius=8,
                            )
                        ],
                    )
                )
                continue

            is_out = msg.get("sender_id") == user_id
            bubble_bg = c["bubble_out"] if is_out else c["bubble_in"]
            radius = (
                ft.BorderRadius.only(top_left=12, top_right=2, bottom_left=12, bottom_right=12)
                if is_out
                else ft.BorderRadius.only(top_left=2, top_right=12, bottom_left=12, bottom_right=12)
            )

            inner_controls: list[ft.Control] = []

            # В общем чате показываем имя отправителя
            if active_room_id == "general" and not is_out:
                inner_controls.append(
                    ft.Text(
                        msg.get("sender_name", "Гость"),
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=msg.get("sender_color", c["accent"]),
                    )
                )

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
                                ft.Text(
                                    rt["text"],
                                    size=12,
                                    color=c["text_secondary"],
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                        ),
                    )
                )

            inner_controls.append(
                ft.Text(msg.get("text", ""), size=14.2, color=c["text_primary"], selectable=True)
            )

            meta_items: list[ft.Control] = [
                ft.Text(msg.get("time", ""), size=11, color=c["text_secondary"]),
            ]
            if is_out:
                meta_items.append(ft.Icon(icon=ft.Icons.DONE_ALL, size=15, color=c["check_read"]))

            action_menu = ft.PopupMenuButton(
                icon=ft.Icons.MORE_HORIZ,
                icon_size=15,
                icon_color=c["text_secondary"],
                tooltip="Действия",
                items=[
                    ft.PopupMenuItem(content="Ответить", on_click=lambda e, m=msg: set_reply(m)),
                    ft.PopupMenuItem(
                        content="Копировать",
                        on_click=lambda e, txt=msg.get("text", ""): page.run_task(copy_message_text, txt),
                    ),
                ],
            )

            inner_controls.append(
                ft.Row(alignment=ft.MainAxisAlignment.END, spacing=4, controls=[action_menu, *meta_items])
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

        # Быстрые кнопки для чат-бота с заготовленными сообщениями
        quick_buttons_row.controls.clear()
        if active_room_id == "bot":
            for label in bot_quick_buttons:
                quick_buttons_row.controls.append(
                    ft.Container(
                        content=ft.Text(label, size=12.5, color=c["accent"]),
                        bgcolor=c["bg_header"],
                        border=ft.Border.all(1, c["border"]),
                        border_radius=999,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=11),
                        on_click=lambda e, txt=label: send_message(txt),
                    )
                )

    def send_message(custom_text: str | None = None) -> None:
        nonlocal bot_quick_buttons
        if not joined:
            return
        text = (custom_text if custom_text is not None else (msg_input.value or "")).strip()
        if not text:
            return
        if custom_text is None:
            msg_input.value = ""

        msg: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "room_id": active_room_id,
            "kind": "chat",
            "sender_id": user_id,
            "sender_name": user_name,
            "sender_color": user_color,
            "text": text,
            "time": now_hhmm(),
        }
        if reply_target:
            msg["reply_to"] = dict(reply_target)
            clear_reply()

        if active_room_id == "saved":
            saved_messages.append(msg)
            render_all()
            return

        if active_room_id == "bot":
            bot_messages.append(msg)
            online_names = [u["name"] for u in get_online_snapshot()]
            reply_text, next_buttons = get_bot_reply(text, online_names)
            bot_quick_buttons = next_buttons
            bot_messages.append(
                {
                    "id": uuid.uuid4().hex,
                    "room_id": "bot",
                    "kind": "chat",
                    "sender_id": "bot",
                    "sender_name": "Бот-Помощник",
                    "sender_color": "#2b6cb0",
                    "text": reply_text,
                    "time": now_hhmm(),
                }
            )
            render_all()
            return

        # Общий чат или личный чат с другим пользователем — рассылаем в реальном времени!
        append_room_message(active_room_id, msg)
        page.pubsub.send_all({"type": "message", "room_id": active_room_id, "message": msg})

    # PubSub: получение живых событий от других посетителей сайта
    def on_pubsub_event(event: dict[str, Any]) -> None:
        if not joined:
            return
        ev_type = event.get("type")

        if ev_type == "presence":
            render_sidebar()
            render_header()
            page.update()
            return

        if ev_type == "message":
            room_id = event.get("room_id", "")
            msg = event.get("message") or {}

            # Личные сообщения доставляем только двум участникам этой комнаты
            if room_id.startswith("dm:"):
                parts = room_id.split(":")
                if user_id not in parts[1:]:
                    return
                if msg.get("sender_id") != user_id:
                    known_peers[msg["sender_id"]] = {
                        "id": msg["sender_id"],
                        "name": msg.get("sender_name", "Гость"),
                        "color": msg.get("sender_color", "#00a884"),
                    }

            if room_id != active_room_id and msg.get("sender_id") != user_id and msg.get("kind") != "system":
                unread_counts[room_id] = unread_counts.get(room_id, 0) + 1

            render_all()

    page.pubsub.subscribe(on_pubsub_event)

    def broadcast_system_general(text: str) -> None:
        sys_msg = {
            "id": uuid.uuid4().hex,
            "room_id": "general",
            "kind": "system",
            "text": text,
            "time": now_hhmm(),
        }
        append_room_message("general", sys_msg)
        page.pubsub.send_all({"type": "message", "room_id": "general", "message": sys_msg})

    def on_disconnect(_e) -> None:
        if not joined:
            return
        removed_name = ""
        with STATE_LOCK:
            info = ONLINE_USERS.pop(user_id, None)
            if info:
                removed_name = info["name"]
        try:
            page.pubsub.unsubscribe_all()
        except Exception:
            pass
        if removed_name:
            broadcast_system_general(f"{removed_name} вышел из чата")
            page.pubsub.send_all({"type": "presence"})

    page.on_disconnect = on_disconnect

    # Диалог смены имени
    def open_profile_dialog(_=None) -> None:
        name_tf = ft.TextField(label="Ваше имя в чате", value=user_name, max_length=24)

        def save_name(_e) -> None:
            nonlocal user_name
            new_name = (name_tf.value or "").strip()
            if not new_name:
                show_snack("Имя не может быть пустым")
                return
            old_name = user_name
            user_name = new_name
            with STATE_LOCK:
                if user_id in ONLINE_USERS:
                    ONLINE_USERS[user_id]["name"] = user_name
            page.pop_dialog()
            if old_name != new_name:
                broadcast_system_general(f"{old_name} сменил имя на {new_name}")
            page.pubsub.send_all({"type": "presence"})
            render_all()

        dlg = ft.AlertDialog(
            title=ft.Text("Ваш профиль"),
            content=ft.Container(width=340, content=name_tf),
            actions=[
                ft.TextButton(content="Отмена", on_click=lambda _: page.pop_dialog()),
                ft.Button(content="Сохранить", on_click=save_name),
            ],
        )
        page.show_dialog(dlg)

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

    search_field.on_change = on_search_change
    msg_input.on_submit = lambda e: send_message()
    send_btn.on_click = lambda e: send_message()
    theme_btn.on_click = toggle_theme
    profile_btn.on_click = open_profile_dialog
    back_btn.on_click = on_mobile_back

    sidebar_header = ft.Container(height=60, padding=ft.Padding.symmetric(horizontal=12))
    search_wrap = ft.Container(padding=ft.Padding.only(left=12, right=12, top=8, bottom=8))
    sidebar_panel = ft.Container(width=340)

    chat_header = ft.Container(height=60, padding=ft.Padding.symmetric(horizontal=12))
    quick_bar = ft.Container(padding=ft.Padding.symmetric(vertical=4, horizontal=16), content=quick_buttons_row)
    composer_box = ft.Container(
        border_radius=12,
        padding=ft.Padding.symmetric(vertical=2, horizontal=12),
        expand=True,
        content=msg_input,
    )
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
                        me_avatar_circle,
                        ft.Column(
                            spacing=0,
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[me_name_txt, online_counter_txt],
                        ),
                    ],
                ),
                ft.Row(spacing=0, controls=[theme_btn, profile_btn]),
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
                                ft.Row(spacing=6, controls=[active_title_txt, active_badge]),
                                active_status_txt,
                            ],
                        ),
                    ],
                ),
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
        if joined:
            apply_layout()
            render_messages()
            page.update()

    page.on_resize = on_resize

    # Экран входа (выбор имени и цвета аватара)
    selected_color_ref = [user_color]
    name_input = ft.TextField(
        label="Ваше имя",
        hint_text="Например: Максим",
        autofocus=True,
        max_length=24,
    )
    color_row = ft.Row(spacing=8, alignment=ft.MainAxisAlignment.CENTER)

    def render_color_picker() -> None:
        color_row.controls.clear()
        for col in AVATAR_COLORS:
            picked = col == selected_color_ref[0]
            color_row.controls.append(
                ft.Container(
                    width=28,
                    height=28,
                    border_radius=14,
                    bgcolor=col,
                    border=ft.Border.all(2.5, "#ffffff") if picked else None,
                    on_click=lambda e, cl=col: pick_color(cl),
                )
            )

    def pick_color(col: str) -> None:
        selected_color_ref[0] = col
        render_color_picker()
        page.update()

    def enter_chat(_e=None) -> None:
        nonlocal user_name, user_color, joined
        entered = (name_input.value or "").strip()
        if not entered:
            show_snack("Введите ваше имя, чтобы зайти в чат")
            return
        user_name = entered
        user_color = selected_color_ref[0]
        joined = True

        with STATE_LOCK:
            ONLINE_USERS[user_id] = {"id": user_id, "name": user_name, "color": user_color}

        page.controls.clear()
        page.add(root_row)
        render_all()

        broadcast_system_general(f"{user_name} присоединился к чату")
        page.pubsub.send_all({"type": "presence"})

    name_input.on_submit = enter_chat
    render_color_picker()

    c = colors()
    page.bgcolor = c["bg_app"]
    login_card = ft.Container(
        width=360,
        padding=24,
        border_radius=16,
        bgcolor=c["bg_sidebar"],
        border=ft.Border.all(1, c["border"]),
        content=ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[
                ft.Container(
                    width=56,
                    height=56,
                    border_radius=28,
                    bgcolor=c["accent"],
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(icon=ft.Icons.CHAT_ROUNDED, color="#ffffff", size=28),
                ),
                ft.Text("PulseChat", size=22, weight=ft.FontWeight.BOLD, color=c["text_primary"]),
                ft.Text(
                    f"Живой мессенджер для общения на сайте · сейчас онлайн: {len(get_online_snapshot())}",
                    size=13,
                    color=c["text_secondary"],
                    text_align=ft.TextAlign.CENTER,
                ),
                name_input,
                ft.Text("Цвет аватара:", size=12, color=c["text_secondary"]),
                color_row,
                ft.Button(
                    content="Войти в мессенджер",
                    width=312,
                    height=44,
                    on_click=enter_chat,
                ),
            ],
        ),
    )

    page.add(
        ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            padding=16,
            content=login_card,
        )
    )


if __name__ == "__main__":
    if os.getenv("PORT") or os.getenv("FLET_FORCE_WEB_SERVER"):
        port = int(os.getenv("PORT", os.getenv("FLET_SERVER_PORT", "8000")))
        ft.run(main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=port)
    else:
        ft.run(main)
else:
    app = ft.run(main, export_asgi_app=True)
