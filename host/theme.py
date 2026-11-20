# -*- coding: utf-8 -*-
"""深色主题配色与字体。"""

from __future__ import annotations

BG = "#060911"
PANEL = "#0A1017"
CARD = "#111A26"
CARD2 = "#0C141F"
STROKE = "#1B2634"
TEXT = "#F2F7FF"
SUB = "#8A98AC"
MUTED = "#5C6A7E"

ACCENT = "#4F8CFF"     # 电脑 → 手机
ACCENT2 = "#9B6BFF"
MINT = "#2FD8A0"       # 手机 → 电脑
CYAN = "#22D3EE"
PINK = "#FF6FAE"       # 双向
OK = "#35D07F"
WARN = "#FFB020"
ERR = "#FF5F6D"

FONT_CANDIDATES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Segoe UI",
)


def pick_font(tkfont) -> str:
    """挑一个能好好显示中文的系统字体。"""
    try:
        families = set(tkfont.families())
    except Exception:
        families = set()
    for name in FONT_CANDIDATES:
        if name in families:
            return name
    return "Segoe UI"
