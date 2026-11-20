# -*- coding: utf-8 -*-
"""手绘组件：渐变按钮、进度条、方向卡片、复选框、头像。

Tkinter 没有圆角也没有渐变，这里都用 Canvas 一点点画出来。
"""

from __future__ import annotations

import colorsys
import tkinter as tk

from theme import ACCENT, ACCENT2, CARD, CARD2, MINT, MUTED, OK, STROKE, SUB, TEXT

WHITE = "#FFFFFF"


# ------------------------------------------------------------------ 颜色工具
def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in rgb[:3])


def blend(a: str, b: str, t: float) -> str:
    ca, cb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex([ca[i] + (cb[i] - ca[i]) * t for i in range(3)])


def mix_bg(color: str, alpha: float, base: str) -> str:
    """把 color 以 alpha 透明度压到 base 上，模拟半透明填充。"""
    return blend(base, color, max(0.0, min(1.0, alpha)))


def hsl_color(hue: float, sat: float = 0.66, light: float = 0.6) -> str:
    r, g, b = colorsys.hls_to_rgb((hue % 360) / 360.0, light, sat)
    return rgb_to_hex((r * 255, g * 255, b * 255))


def initial_of(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return "?"
    first = text[0]
    return first.upper() if first.isascii() and first.isalpha() else first


# ------------------------------------------------------------------ 渐变底
def gradient_fill(canvas: tk.Canvas, x0, y0, x1, y1, c1, c2,
                  horizontal: bool = True, steps: int | None = None,
                  tags: str = "grad") -> None:
    span = (x1 - x0) if horizontal else (y1 - y0)
    if span <= 0:
        return
    steps = steps or max(10, min(220, int(span // 6) or 10))
    for i in range(steps):
        t = i / max(1, steps - 1)
        color = blend(c1, c2, t)
        if horizontal:
            a = x0 + span * i / steps
            b = x0 + span * (i + 1) / steps + 1
            canvas.create_rectangle(a, y0, b, y1, fill=color, outline=color, tags=tags)
        else:
            a = y0 + span * i / steps
            b = y0 + span * (i + 1) / steps + 1
            canvas.create_rectangle(x0, a, x1, b, fill=color, outline=color, tags=tags)


def _corner_masks(canvas: tk.Canvas, x0, y0, x1, y1, r, bg: str, tags="grad") -> None:
    """四个角用 chord 盖掉，比逐像素算圆角快得多。"""
    corners = (
        (x0, y0, x0 + 2 * r, y0 + 2 * r, 90),
        (x1 - 2 * r, y0, x1, y0 + 2 * r, 0),
        (x1 - 2 * r, y1 - 2 * r, x1, y1, 270),
        (x0, y1 - 2 * r, x0 + 2 * r, y1, 180),
    )
    for cx0, cy0, cx1, cy1, start in corners:
        canvas.create_arc(cx0, cy0, cx1, cy1, start=start, extent=90, style=tk.CHORD,
                          fill=bg, outline=bg, tags=tags)


def gradient_round(canvas: tk.Canvas, width: int, height: int, radius: int,
                   c1: str, c2: str, bg: str, horizontal: bool = True,
                   tags: str = "grad") -> None:
    """在画布 0,0,width,height 上画一块渐变圆角矩形（先清空同 tag 的旧图）。"""
    canvas.delete(tags)
    r = max(0, min(radius, height // 2, width // 2))
    gradient_fill(canvas, 0, 0, width, height, c1, c2, horizontal, tags=tags)
    if r > 0:
        _corner_masks(canvas, 0, 0, width - 1, height - 1, r, bg, tags=tags)


def gradient_strip(canvas: tk.Canvas, width: int, height: int, c1: str, c2: str,
                   bg: str) -> None:
    canvas.delete("all")
    gradient_fill(canvas, 0, 0, max(width, 2), height, c1, c2, True, tags="strip")


# ------------------------------------------------------------------ 按钮
class GradientButton(tk.Canvas):
    def __init__(self, parent, text: str, command=None, height: int = 52,
                 bg: str = CARD, colors: tuple[str, str] = (ACCENT, ACCENT2),
                 font=("Segoe UI", 11, "bold"), width: int = 0,
                 text_color: str = WHITE, radius: int | None = None):
        super().__init__(parent, height=height, width=width, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0, cursor="hand2")
        self._text = text
        self._command = command
        self._bg = bg
        self._colors = colors
        self._font = font
        self._text_color = text_color
        self._radius = height // 2 if radius is None else radius
        self._enabled = True
        self._hover = False
        self._cw = width or 200
        self._ch = height
        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_configure(self, event) -> None:
        self._cw = max(2, event.width)
        self._ch = max(2, event.height)
        self._draw()

    def _on_enter(self, _event) -> None:
        self._hover = True
        self._draw()

    def _on_leave(self, _event) -> None:
        self._hover = False
        self._draw()

    def _on_press(self, _event) -> None:
        if self._enabled:
            self._hover = False
            self._draw(pressed=True)

    def _on_release(self, _event) -> None:
        if not self._enabled:
            return
        self._hover = True
        self._draw()
        if self._command:
            self._command()

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)
        self.configure(cursor="hand2" if value else "arrow")
        self._draw()

    def set_text(self, text: str) -> None:
        self._text = text
        self._draw()

    def set_colors(self, colors: tuple[str, str]) -> None:
        self._colors = colors
        self._draw()

    def _draw(self, pressed: bool = False) -> None:
        self.delete("all")
        if self._enabled:
            c1, c2 = self._colors
            if self._hover:
                c1, c2 = blend(c1, WHITE, 0.10), blend(c2, WHITE, 0.10)
            if pressed:
                c1, c2 = blend(c1, "#000000", 0.16), blend(c2, "#000000", 0.16)
            text_color = self._text_color
        else:
            c1, c2 = mix_bg("#FFFFFF", 0.05, self._bg), mix_bg("#FFFFFF", 0.03, self._bg)
            text_color = MUTED

        gradient_round(self, self._cw, self._ch, self._radius, c1, c2, self._bg)
        self.create_text(self._cw // 2, self._ch // 2, text=self._text,
                         fill=text_color, font=self._font)


class GhostButton(tk.Canvas):
    def __init__(self, parent, text: str, command=None, height: int = 36,
                 bg: str = CARD, fg: str = SUB, font=("Segoe UI", 9),
                 width: int = 0, color=STROKE):
        super().__init__(parent, height=height, width=width, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0, cursor="hand2")
        self._text = text
        self._command = command
        self._bg = bg
        self._fg = fg
        self._font = font
        self._cw = width or 90
        self._ch = height
        self._hover = False
        self._color = color
        self._enabled = True
        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_configure(self, event) -> None:
        self._cw = max(2, event.width)
        self._ch = max(2, event.height)
        self._draw()

    def _on_enter(self, _event) -> None:
        self._hover = True
        self._draw()

    def _on_leave(self, _event) -> None:
        self._hover = False
        self._draw()

    def _on_release(self, _event) -> None:
        if self._enabled and self._command:
            self._command()

    def set_text(self, text: str) -> None:
        self._text = text
        self._draw()

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)
        self._hover = False
        self.configure(cursor="hand2" if value else "arrow")
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        r = self._ch // 2
        fill = mix_bg("#FFFFFF", 0.08 if self._hover else 0.04, self._bg)
        _round_rect(self, 0, 0, self._cw - 1, self._ch - 1, r, fill=fill,
                    outline=self._color)
        self.create_text(self._cw // 2, self._ch // 2, text=self._text,
                         fill=self._fg if self._enabled else MUTED, font=self._font)


def _round_rect(canvas: tk.Canvas, x0, y0, x1, y1, r, fill: str, outline: str = "",
                width: int = 1, tags: str = "") -> None:
    r = max(0, min(r, (x1 - x0) // 2, (y1 - y0) // 2))
    points = [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
    ]
    canvas.create_polygon(points, smooth=True, splinesteps=12,
                          fill=fill, outline=outline, width=width, tags=tags)


# ------------------------------------------------------------------ 进度条
class ProgressBar(tk.Canvas):
    def __init__(self, parent, height: int = 10, bg: str = CARD,
                 colors: tuple[str, str] = (ACCENT, ACCENT2), width: int = 0):
        super().__init__(parent, height=height, width=width, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self._bg = bg
        self._colors = colors
        self._value = 0.0
        self._cw = width or 300
        self._ch = height
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event) -> None:
        self._cw = max(2, event.width)
        self._ch = max(2, event.height)
        self._draw()

    def set_value(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if abs(value - self._value) < 0.002 and value not in (0.0, 1.0):
            return
        self._value = value
        self._draw()

    def set_colors(self, colors: tuple[str, str]) -> None:
        self._colors = colors
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        r = self._ch // 2
        _round_rect(self, 0, 0, self._cw - 1, self._ch - 1, r,
                    fill=mix_bg("#FFFFFF", 0.07, self._bg))
        if self._value <= 0:
            return
        fill_w = max(self._ch, int((self._cw - 1) * self._value))
        c1, c2 = self._colors
        self.create_rectangle(0, 0, fill_w + 1, self._ch, fill=c1, outline="")
        # 进度条内部也做一段渐变，看起来更有质感
        steps = max(8, min(120, fill_w // 4))
        for i in range(steps):
            a = fill_w * i / steps
            b = fill_w * (i + 1) / steps + 1
            self.create_rectangle(a, 0, b, self._ch, fill=blend(c1, c2, i / steps),
                                  outline="")
        _corner_masks(self, 0, 0, fill_w, self._ch - 1, r, self._bg, tags="bar")


# ------------------------------------------------------------------ 头像
class Avatar(tk.Canvas):
    def __init__(self, parent, name: str, hue: int, size: int = 42, bg: str = CARD,
                 icon: bool = True):
        super().__init__(parent, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        base = hsl_color(hue, 0.62, 0.55)
        top = hsl_color(hue, 0.72, 0.68)
        self.create_oval(0, 0, size - 1, size - 1, fill=base, outline=blend(base, WHITE, 0.35))
        self.create_oval(2, 2, size - 3, int(size * 0.72), fill=top, outline="")
        self.create_oval(2, 2, size - 3, size - 3, outline=blend(base, WHITE, 0.25))
        if icon:
            self._glyph("手机", size)
        else:
            self.create_text(size // 2, size // 2, text=initial_of(name), fill=WHITE,
                             font=("Segoe UI", int(size * 0.38), "bold"))

    def _glyph(self, _kind: str, size: int) -> None:
        s = size / 42.0
        self.create_rectangle(13 * s, 8 * s, 29 * s, 34 * s,
                              outline=WHITE, width=max(1, int(round(2 * s))), fill="")
        self.create_rectangle(16 * s, 12 * s, 26 * s, 28 * s, fill="#EAF2FF", outline="")
        self.create_oval(19 * s, 29.5 * s, 23 * s, 31.5 * s, fill=WHITE, outline="")


# ------------------------------------------------------------------ 复选框
class CheckBox(tk.Frame):
    def __init__(self, parent, text: str, value: bool = False, bg: str = CARD,
                 command=None, hint: str = "", font_family: str = "Segoe UI"):
        super().__init__(parent, bg=bg)
        self._value = bool(value)
        self._bg = bg
        self._command = command

        self.box = tk.Canvas(self, width=18, height=18, bg=bg,
                             highlightthickness=0, bd=0, takefocus=0, cursor="hand2")
        self.box.pack(side="left", pady=(1, 0))

        col = tk.Frame(self, bg=bg)
        col.pack(side="left", fill="x", expand=True, padx=(9, 0))
        self.label = tk.Label(col, text=text, bg=bg, fg=TEXT,
                              font=(font_family, 9), anchor="w", cursor="hand2")
        self.label.pack(fill="x")
        self.hint_label = None
        if hint:
            self.hint_label = tk.Label(col, text=hint, bg=bg, fg=MUTED,
                                       font=(font_family, 8), anchor="w", cursor="hand2")
            self.hint_label.pack(fill="x")

        for widget in (self, self.box, col, self.label, self.hint_label):
            if widget is not None:
                widget.bind("<Button-1>", self._toggle)
        self._draw()

    @property
    def value(self) -> bool:
        return self._value

    def set_value(self, value: bool, notify: bool = False) -> None:
        self._value = bool(value)
        self._draw()
        if notify and self._command:
            self._command(self._value)

    def _toggle(self, _event=None) -> None:
        self._value = not self._value
        self._draw()
        if self._command:
            self._command(self._value)

    def _draw(self) -> None:
        self.box.delete("all")
        if self._value:
            self.box.create_rectangle(1, 1, 17, 17, fill=ACCENT, outline=ACCENT)
            self.box.create_line(5, 9, 8, 12, 13, 6, fill=WHITE, width=2,
                                 capstyle=tk.ROUND, joinstyle=tk.ROUND)
        else:
            self.box.create_rectangle(1, 1, 17, 17, fill=mix_bg("#FFFFFF", 0.03, self._bg),
                                      outline=STROKE)


# ------------------------------------------------------------------ 方向卡片
class DirectionTile(tk.Frame):
    """一行可点的方向选项，选中时左侧亮一条渐变细线。"""

    def __init__(self, parent, key: str, title: str, subtitle: str,
                 colors: tuple[str, str], badge: str = "", bg: str = CARD,
                 font_family: str = "Segoe UI", command=None):
        super().__init__(parent, bg=bg)
        self.key = key
        self._bg = bg
        self._colors = colors
        self._selected = False
        self._command = command
        self.configure(highlightthickness=1, highlightbackground=STROKE,
                       highlightcolor=STROKE)

        self.outer = tk.Frame(self, bg=bg)
        self.outer.pack(fill="x", expand=True)

        self.bar = tk.Canvas(self.outer, width=4, height=54, bg=bg, highlightthickness=0, bd=0)
        self.bar.pack(side="left", fill="y")

        self.icon = tk.Canvas(self.outer, width=30, height=30, bg=bg,
                              highlightthickness=0, bd=0)
        self.icon.pack(side="left", padx=(9, 9), pady=9)

        self.col = tk.Frame(self.outer, bg=bg)
        self.col.pack(side="left", fill="x", expand=True, pady=7)
        self.title_label = tk.Label(self.col, text=title, bg=bg, fg=TEXT,
                                    font=(font_family, 10, "bold"), anchor="w")
        self.title_label.pack(fill="x")
        self.sub_label = tk.Label(self.col, text=subtitle, bg=bg, fg=MUTED,
                                  font=(font_family, 8), anchor="w")
        self.sub_label.pack(fill="x")

        self.right = tk.Frame(self.outer, bg=bg)
        self.right.pack(side="right", padx=(6, 10))
        self.badge = tk.Label(self.right, text=badge, bg=bg, fg=ACCENT2,
                              font=(font_family, 8, "bold"))
        if badge:
            self.badge.pack(anchor="e")
        self.radio = tk.Canvas(self.right, width=16, height=16, bg=bg,
                               highlightthickness=0, bd=0)
        self.radio.pack(anchor="e", pady=(3, 0))

        targets = [self, self.outer, self.bar, self.icon, self.col,
                   self.title_label, self.sub_label, self.right, self.badge, self.radio]
        for widget in targets:
            widget.bind("<Button-1>", self._click)
            widget.configure(cursor="hand2")

        self._draw()

    def _click(self, _event=None) -> None:
        if self._command:
            self._command(self.key)

    def set_selected(self, value: bool) -> None:
        self._selected = bool(value)
        self._draw()

    def _draw(self) -> None:
        bg = mix_bg(self._colors[0], 0.16, CARD2) if self._selected else self._bg
        border = blend(STROKE, self._colors[0], 0.55) if self._selected else STROKE
        for widget in (self, self.outer, self.col, self.right, self.icon, self.bar, self.radio):
            widget.configure(bg=bg)
        for widget in (self.title_label, self.sub_label, self.badge):
            widget.configure(bg=bg)
        self.configure(highlightbackground=border, highlightcolor=border)

        self.bar.delete("all")
        if self._selected:
            gradient_fill(self.bar, 0, 0, 4, 54, self._colors[0], self._colors[1],
                          horizontal=False, steps=18, tags="bar")

        self.icon.delete("all")
        gradient_round(self.icon, 30, 30, 9, self._colors[0], self._colors[1], bg)
        self.icon.create_text(15, 15, text="↑" if self.key == "pull" else "↓"
                              if self.key == "push" else "⇅",
                              fill=WHITE, font=("Segoe UI", 11, "bold"))

        self.radio.delete("all")
        if self._selected:
            self.radio.create_oval(1, 1, 15, 15, outline=self._colors[0], width=2)
            self.radio.create_oval(5, 5, 11, 11, fill=self._colors[0], outline="")
        else:
            self.radio.create_oval(1, 1, 15, 15, outline=STROKE, width=2)


# ------------------------------------------------------------------ 小标签
class Pill(tk.Label):
    def __init__(self, parent, text: str, color: str = ACCENT, bg: str = CARD,
                 font_family: str = "Segoe UI", size: int = 8):
        super().__init__(parent, text=text, bg=mix_bg(color, 0.16, bg), fg=color,
                         font=(font_family, size, "bold"), padx=9, pady=3)


def dot(canvas: tk.Canvas, x: int, y: int, color: str, r: int = 4) -> None:
    canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")


__all__ = [
    "GradientButton", "GhostButton", "ProgressBar", "Avatar", "CheckBox",
    "DirectionTile", "Pill", "blend", "mix_bg", "hsl_color", "initial_of",
    "gradient_fill", "gradient_round", "gradient_strip", "dot", "OK", "ACCENT",
    "ACCENT2", "MINT", "TEXT", "SUB", "MUTED", "CARD", "CARD2", "STROKE",
]
