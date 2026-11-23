# -*- coding: utf-8 -*-
"""Tkinter 主界面：左边选文件夹和方向，右边选手机、看同步计划。"""

from __future__ import annotations

import os
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from config import (
    APP_NAME,
    APP_VER,
    DISCOVERY_PORT,
    MODE_PULL,
    MODE_PUSH,
    MODE_TWO,
    PROTO_VER,
    default_root,
    human_size,
    local_ip,
    mode_label,
    short_path,
    update_config,
)
import lanscan
import netinfo
from discovery import beacon_loop, discovery_loop
from draw import (
    Avatar,
    CheckBox,
    DirectionTile,
    GhostButton,
    GradientButton,
    ProgressBar,
    blend,
    dot,
    gradient_round,
    gradient_strip,
    mix_bg,
)
from server import start_http
from state import HostState
from sync import PeerClient, SyncRunner
from theme import (
    ACCENT,
    ACCENT2,
    BG,
    CARD,
    CARD2,
    CYAN,
    ERR,
    MINT,
    MUTED,
    OK,
    PANEL,
    PINK,
    STROKE,
    SUB,
    TEXT,
    WARN,
    pick_font,
)

MODE_COLORS = {
    MODE_PUSH: (ACCENT, ACCENT2),
    MODE_PULL: (MINT, CYAN),
    MODE_TWO: (PINK, ACCENT2),
}

MODE_DESC = {
    MODE_PUSH: "电脑上的新文件覆盖到手机，日常最常用",
    MODE_PULL: "手机上的新文件覆盖到电脑",
    MODE_TWO: "两边取新、缺的补齐，谁也丢不了",
}

MAX_ROWS = 4000


def bundled_icon() -> Path | None:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for name in ("icon.ico", "app.ico"):
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


class HostApp:
    def __init__(self, state: HostState, port: int, cfg: dict):
        import tkinter.font as tkfont

        self.state = state
        self.port = port
        self.cfg = cfg
        self.stop = threading.Event()
        self.font = pick_font(tkfont)

        self.mode = str(cfg.get("mode") or MODE_PUSH)
        if self.mode not in MODE_COLORS:
            self.mode = MODE_PUSH
        self.selected_peer_id = str(cfg.get("peer_id") or "")
        self.peers: list[dict] = []
        self._peer_sig = None
        self._nudge = ""
        self._scanning = False
        self._tiles: dict[str, DirectionTile] = {}

        self.running = False
        self.dry_run = False
        self.plan_iids: dict[str, str] = {}
        self.total_bytes = 0
        self.done_bytes = 0
        self.cur_rel = ""
        self.cur_done = 0
        self.cur_total = 0
        self.counts = {"up": 0, "down": 0, "skip": 0, "fail": 0}
        self._started_at = 0.0
        self._finish_stats: dict = {}
        self._last_status = ""

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} · 同网双向同步")
        self.root.configure(bg=BG)
        self.root.geometry("1240x900")
        self.root.minsize(1080, 760)

        icon = bundled_icon()
        if icon is not None:
            try:
                self.root.iconbitmap(default=str(icon))
            except Exception:
                pass

        self._build()
        self._start_servers()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(80, self._dark_titlebar)
        self.root.after(120, self._poll)

    # ------------------------------------------------------------ 启动
    def _start_servers(self) -> None:
        self.server = start_http(self.state, self.port)
        if self.server is None:
            self.set_footer(f"HTTP 端口 {self.port} 打不开，可能被防火墙或其他程序占用")
        self.port = self.state.port
        threading.Thread(target=discovery_loop, args=(self.state, self.stop), daemon=True).start()
        threading.Thread(target=beacon_loop, args=(self.state, self.stop), daemon=True).start()
        self.addr_label.configure(text=f"{local_ip()}:{self.port}")
        self.set_footer("已就绪：手机打开 SynSimplify，同一个 WiFi 会自动发现这台电脑")

        # 常见坑：无线网卡在，但压根没连上 WiFi（只有网线）
        if netinfo.wireless_down() and not [n for n in netinfo.nics() if n.wireless]:
            self.set_footer("提示：检测到无线网卡但未连接 WiFi —— 手机若走 WiFi，需要先让电脑连上同一个无线网络")

    def _dark_titlebar(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            flag = ctypes.c_int(1)
            for attr in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(flag), ctypes.sizeof(flag))
        except Exception:
            pass

    def _on_close(self) -> None:
        self.state.cancel.set()
        self.stop.set()
        try:
            self.server.shutdown()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------ 界面
    def _build(self) -> None:
        root = self.root
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        strip = tk.Canvas(root, height=3, bg=BG, highlightthickness=0, bd=0)
        strip.grid(row=0, column=0, sticky="ew")
        strip.bind("<Configure>", lambda e: gradient_strip(strip, e.width, 3, ACCENT, ACCENT2, BG))

        self._build_header()

        body = tk.Frame(root, bg=BG)
        body.grid(row=2, column=0, sticky="nsew", padx=20)

        # 左栏卡片较多，窗口不高时会超出底部，放进画布用滚轮上下看
        left_wrap = tk.Frame(body, bg=BG, width=356)
        left_wrap.pack(side="left", fill="y")
        left_wrap.pack_propagate(False)

        left_canvas = tk.Canvas(left_wrap, bg=BG, highlightthickness=0, bd=0)
        left_canvas.pack(side="left", fill="both", expand=True)
        left = tk.Frame(left_canvas, bg=BG)
        left_win = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _sync_left(_event=None) -> None:
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))
            left_canvas.itemconfigure(left_win, width=left_canvas.winfo_width())

        def _on_left_wheel(event) -> None:
            box = left_canvas.bbox("all")
            if not box or box[3] <= left_canvas.winfo_height():
                return
            left_canvas.yview_scroll(-1 if getattr(event, "delta", 0) > 0 else 1, "units")

        left.bind("<Configure>", _sync_left)
        left_canvas.bind("<Configure>", _sync_left)

        self._build_folder_cards(left)
        self._build_direction_card(left)
        self._build_options_card(left)
        self._build_buttons(left)

        self._bind_wheel(left, _on_left_wheel)
        left_canvas.bind("<MouseWheel>", _on_left_wheel)

        self._build_right(body)

        footer = tk.Frame(root, bg=BG)
        footer.grid(row=3, column=0, sticky="ew", padx=22, pady=(10, 12))
        footer.grid_columnconfigure(0, weight=1)
        self.footer_label = tk.Label(footer, text="启动中…", bg=BG, fg=MUTED,
                                     font=(self.font, 9), anchor="w")
        self.footer_label.grid(row=0, column=0, sticky="w")
        tk.Label(footer, text=f"v{APP_VER} · 协议 v{PROTO_VER} · 端口 {DISCOVERY_PORT}/{self.port}",
                 bg=BG, fg=MUTED, font=(self.font, 9)).grid(row=0, column=1, sticky="e")

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.grid(row=1, column=0, sticky="ew", padx=22, pady=(16, 14))
        header.grid_columnconfigure(2, weight=1)

        logo = tk.Canvas(header, width=48, height=48, bg=BG, highlightthickness=0, bd=0)
        logo.grid(row=0, column=0, rowspan=2, sticky="w")
        gradient_round(logo, 48, 48, 15, ACCENT, ACCENT2, BG)
        # 双向箭头：下箭头（电脑→手机）+ 上箭头（手机→电脑）
        logo.create_line(18, 13, 18, 33, fill="#FFFFFF", width=3, capstyle=tk.ROUND)
        logo.create_polygon(13, 27, 23, 27, 18, 36, fill="#FFFFFF", outline="")
        logo.create_line(31, 36, 31, 16, fill="#EAF1FF", width=3, capstyle=tk.ROUND)
        logo.create_polygon(26, 22, 36, 22, 31, 13, fill="#EAF1FF", outline="")

        tk.Label(header, text="SynSimplify", bg=BG, fg=TEXT,
                 font=(self.font, 19, "bold")).grid(row=0, column=1, sticky="sw", padx=(13, 0))
        tk.Label(header, text="同一 WiFi · 双向文件夹同步", bg=BG, fg=SUB,
                 font=(self.font, 9)).grid(row=1, column=1, sticky="nw", padx=(13, 0))

        right = tk.Frame(header, bg=BG)
        right.grid(row=0, column=3, rowspan=2, sticky="e")
        status_row = tk.Frame(right, bg=BG)
        status_row.pack(anchor="e")
        self.status_dot = tk.Canvas(status_row, width=10, height=10, bg=BG,
                                    highlightthickness=0, bd=0)
        self.status_dot.pack(side="left", pady=(1, 0))
        dot(self.status_dot, 5, 5, WARN)
        self.status_label = tk.Label(status_row, text="等待手机连接", bg=BG, fg=WARN,
                                     font=(self.font, 10, "bold"))
        self.status_label.pack(side="left", padx=(7, 0))

        self.addr_label = tk.Label(right, text="0.0.0.0:37121", bg=BG, fg=ACCENT,
                                   font=(self.font, 9), cursor="hand2")
        self.addr_label.pack(anchor="e", pady=(4, 0))
        self.addr_label.bind("<Button-1>", lambda e: self.copy_address())

    @staticmethod
    def _bind_wheel(widget, handler) -> None:
        """tk 的滚轮事件不会冒泡，得挨个控件绑一遍。"""
        for child in widget.winfo_children():
            HostApp._bind_wheel(child, handler)
        try:
            widget.bind("<MouseWheel>", handler)
        except Exception:  # noqa: BLE001
            pass

    def _card(self, parent, title: str):
        outer = tk.Frame(parent, bg=CARD, highlightbackground=STROKE, highlightthickness=1)
        outer.pack(fill="x", pady=(0, 11))
        inner = tk.Frame(outer, bg=CARD, padx=14, pady=11)
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text=title, bg=CARD, fg=MUTED,
                 font=(self.font, 8, "bold")).pack(anchor="w")
        return inner

    def _build_folder_cards(self, parent) -> None:
        inner = self._card(parent, "本机文件夹 · 电脑")
        self.dir_label = tk.Label(inner, text="", bg=CARD, fg=TEXT, font=(self.font, 9),
                                  wraplength=292, justify="left", anchor="w")
        self.dir_label.pack(anchor="w", pady=(7, 3))
        self.dir_hint = tk.Label(inner, text="手机端会把这个文件夹当作同步目标", bg=CARD,
                                 fg=MUTED, font=(self.font, 8), anchor="w",
                                 justify="left", wraplength=292)
        self.dir_hint.pack(anchor="w", pady=(0, 9))

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x")
        GradientButton(row, "选择文件夹", command=self.pick_folder, width=126, height=34,
                       bg=CARD, font=(self.font, 9, "bold")).pack(side="left")
        GhostButton(row, "打开", command=self.open_root, width=64, height=34,
                    bg=CARD, font=(self.font, 9)).pack(side="left", padx=(8, 0))
        self._refresh_dir_label()

        inner2 = self._card(parent, "手机文件夹 · 对端")
        self.remote_label = tk.Label(inner2, text="连上手机后显示", bg=CARD, fg=TEXT,
                                     font=(self.font, 9), wraplength=292,
                                     justify="left", anchor="w")
        self.remote_label.pack(anchor="w", pady=(7, 3))
        self.remote_hint = tk.Label(inner2, text="手机上可以随时换一个文件夹", bg=CARD,
                                    fg=MUTED, font=(self.font, 8), anchor="w",
                                    justify="left", wraplength=292)
        self.remote_hint.pack(anchor="w")

    def _build_direction_card(self, parent) -> None:
        inner = self._card(parent, "同步方向")
        holder = tk.Frame(inner, bg=CARD)
        holder.pack(fill="x", pady=(8, 0))

        specs = (
            (MODE_PUSH, "电脑 → 手机", MODE_DESC[MODE_PUSH], "推荐"),
            (MODE_PULL, "手机 → 电脑", MODE_DESC[MODE_PULL], ""),
            (MODE_TWO, "双向同步", MODE_DESC[MODE_TWO], "稳"),
        )
        for key, title, desc, badge in specs:
            tile = DirectionTile(holder, key, title, desc, MODE_COLORS[key], badge,
                                 bg=CARD, font_family=self.font, command=self.set_mode)
            tile.pack(fill="x", pady=(0, 6))
            self._tiles[key] = tile
        self._paint_mode()

    def _build_options_card(self, parent) -> None:
        inner = self._card(parent, "选项")
        self.cb_delete = CheckBox(
            inner, "删除对端多余的文件", value=bool(self.cfg.get("mirror_delete")),
            bg=CARD, command=self._on_option, hint="镜像效果，只对单向同步生效",
            font_family=self.font)
        self.cb_delete.pack(fill="x", pady=(9, 8))
        self.cb_hidden = CheckBox(
            inner, "包含隐藏文件", value=bool(self.cfg.get("include_hidden")),
            bg=CARD, command=self._on_option, hint="以 . 开头的文件和文件夹",
            font_family=self.font)
        self.cb_hidden.pack(fill="x", pady=(0, 8))

        self.cb_wifi = CheckBox(
            inner, "只从 WiFi 找设备", value=self.state.discover_mode == "wifi",
            bg=CARD, command=self._on_discover_mode,
            hint="网线和 WiFi 同时连着时勾上，广播只走无线网卡",
            font_family=self.font)
        self.cb_wifi.pack(fill="x")

    def _build_buttons(self, parent) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(2, 0))
        self.btn_preview = GhostButton(row, "预览差异", command=lambda: self.start_sync(True),
                                       width=104, height=52, bg=BG, fg=SUB,
                                       font=(self.font, 9), color=STROKE)
        self.btn_preview.pack(side="left")
        self.btn_sync = GradientButton(row, "立即同步", command=lambda: self.start_sync(False),
                                       height=52, bg=BG, colors=MODE_COLORS[self.mode],
                                       font=(self.font, 12, "bold"))
        self.btn_sync.pack(side="left", fill="x", expand=True, padx=(9, 0))

    def _build_right(self, parent) -> None:
        panel = tk.Frame(parent, bg=PANEL, highlightbackground=STROKE, highlightthickness=1)
        panel.pack(side="left", fill="both", expand=True, padx=(16, 0))
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        head = tk.Frame(panel, bg=PANEL)
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(13, 6))
        head.grid_columnconfigure(2, weight=1)
        tk.Label(head, text="手机", bg=PANEL, fg=TEXT,
                 font=(self.font, 12, "bold")).grid(row=0, column=0, sticky="w")
        self.peer_badge = tk.Label(head, text="0 台", bg=mix_bg(ACCENT, 0.16, PANEL),
                                   fg=ACCENT, font=(self.font, 8, "bold"), padx=8, pady=2)
        self.peer_badge.grid(row=0, column=1, sticky="w", padx=(9, 0))
        self.btn_scan = GhostButton(head, "扫描本网络", command=self.scan_lan, width=96,
                                    height=30, bg=PANEL, fg=ACCENT, font=(self.font, 8))
        self.btn_scan.grid(row=0, column=3, sticky="e", padx=(0, 8))
        GhostButton(head, "打开文件夹", command=self.open_root, width=96, height=30,
                    bg=PANEL, fg=SUB, font=(self.font, 8)).grid(row=0, column=4, sticky="e")

        self.peer_box = tk.Frame(panel, bg=PANEL)
        self.peer_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        mid = tk.Frame(panel, bg=PANEL)
        mid.grid(row=2, column=0, sticky="nsew", padx=16)
        mid.grid_rowconfigure(1, weight=1)
        mid.grid_columnconfigure(0, weight=1)

        head2 = tk.Frame(mid, bg=PANEL)
        head2.grid(row=0, column=0, sticky="ew", pady=(4, 7))
        head2.grid_columnconfigure(2, weight=1)
        tk.Label(head2, text="同步计划", bg=PANEL, fg=TEXT,
                 font=(self.font, 12, "bold")).grid(row=0, column=0, sticky="w")
        self.plan_badge = tk.Label(head2, text="待同步", bg=mix_bg(MINT, 0.14, PANEL),
                                   fg=MINT, font=(self.font, 8, "bold"), padx=8, pady=2)
        self.plan_badge.grid(row=0, column=1, sticky="w", padx=(9, 0))

        tree_holder = tk.Frame(mid, bg=PANEL)
        tree_holder.grid(row=1, column=0, sticky="nsew")
        tree_holder.grid_rowconfigure(0, weight=1)
        tree_holder.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Sync.Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, borderwidth=0, rowheight=28,
                        font=(self.font, 9))
        style.configure("Sync.Treeview.Heading", background=CARD, foreground=SUB,
                        borderwidth=0, relief="flat", font=(self.font, 8, "bold"),
                        padding=(6, 8))
        style.map("Sync.Treeview.Heading", background=[("active", CARD)],
                  foreground=[("active", TEXT)])
        style.map("Sync.Treeview", background=[("selected", mix_bg(ACCENT, 0.24, PANEL))],
                  foreground=[("selected", TEXT)])


        self.tree = ttk.Treeview(tree_holder, columns=("dir", "file", "size", "state"),
                                 show="headings", style="Sync.Treeview",
                                 selectmode="browse")
        self.tree.heading("dir", text="方向")
        self.tree.heading("file", text="文件")
        self.tree.heading("size", text="大小")
        self.tree.heading("state", text="状态")
        self.tree.column("dir", width=104, minwidth=90, stretch=False, anchor="w")
        self.tree.column("file", width=340, minwidth=180, stretch=True, anchor="w")
        self.tree.column("size", width=88, minwidth=70, stretch=False, anchor="e")
        self.tree.column("state", width=180, minwidth=120, stretch=False, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scroll = tk.Scrollbar(tree_holder, orient="vertical", command=self.tree.yview,
                              bg=CARD2, troughcolor=PANEL, activebackground=STROKE,
                              highlightthickness=0, bd=0, width=11,
                              elementborderwidth=0, relief="flat")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.tag_configure("push", foreground="#8FB4FF")
        self.tree.tag_configure("pull", foreground="#54E3B4")
        self.tree.tag_configure("del", foreground=ERR)
        self.tree.tag_configure("same", foreground=MUTED)
        self.tree.tag_configure("skip", foreground=WARN)
        self.tree.tag_configure("done", foreground=SUB)
        self.tree.tag_configure("fail", foreground=ERR)
        self.tree.tag_configure("dir", foreground=SUB)

        self._empty_hint = tk.Label(mid, text="选中手机和设备文件夹后，点左下角「立即同步」",
                                    bg=PANEL, fg=MUTED, font=(self.font, 9))
        self._empty_hint.place(relx=0.5, rely=0.56, anchor="center")

        prog = tk.Frame(panel, bg=PANEL)
        prog.grid(row=3, column=0, sticky="ew", padx=16, pady=(12, 14))
        prog.grid_columnconfigure(0, weight=1)

        line = tk.Frame(prog, bg=PANEL)
        line.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        line.grid_columnconfigure(0, weight=1)
        self.file_label = tk.Label(line, text="尚未开始", bg=PANEL, fg=SUB,
                                   font=(self.font, 9), anchor="w")
        self.file_label.grid(row=0, column=0, sticky="w")
        self.bytes_label = tk.Label(line, text="", bg=PANEL, fg=SUB,
                                    font=(self.font, 9), anchor="e")
        self.bytes_label.grid(row=0, column=1, sticky="e", padx=(10, 8))
        self.btn_stop = GhostButton(line, "停止", command=self.stop_sync, width=60, height=26,
                                    bg=PANEL, fg=ERR, font=(self.font, 8), color=blend(STROKE, ERR, 0.4))
        self.btn_stop.grid(row=0, column=2, sticky="e")
        self.btn_stop.grid_remove()

        self.progress = ProgressBar(prog, height=10, bg=PANEL, colors=MODE_COLORS[self.mode])
        self.progress.grid(row=1, column=0, sticky="ew")

        stats = tk.Frame(prog, bg=PANEL)
        stats.grid(row=2, column=0, sticky="ew", pady=(9, 0))
        for i in range(4):
            stats.grid_columnconfigure(i, weight=1)
        self.stat_labels: dict[str, tk.Label] = {}
        for i, (key, label, color) in enumerate((
            ("up", "上行", ACCENT), ("down", "下行", MINT),
            ("skip", "跳过", WARN), ("spend", "耗时", SUB),
        )):
            cell = tk.Frame(stats, bg=CARD2, highlightbackground=STROKE, highlightthickness=1)
            cell.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
            value = tk.Label(cell, text="—", bg=CARD2, fg=color,
                             font=(self.font, 12, "bold"), anchor="w")
            value.pack(fill="x", padx=10, pady=(7, 0))
            tk.Label(cell, text=label, bg=CARD2, fg=MUTED, font=(self.font, 8),
                     anchor="w").pack(fill="x", padx=10, pady=(0, 7))
            self.stat_labels[key] = value

    # ------------------------------------------------------------ 状态
    def set_footer(self, text: str) -> None:
        try:
            self.footer_label.configure(text=text)
        except Exception:
            pass

    def _refresh_dir_label(self) -> None:
        path = str(self.state.get_root())
        self.dir_label.configure(text=short_path(path, 40))
        try:
            is_default = Path(path).resolve() == default_root().resolve()
        except OSError:
            is_default = False
        self.dir_hint.configure(text="默认文件夹 · 手机端会同步到这里" if is_default
                                else "自定义文件夹 · 可随时切换")

    def pick_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(self.state.get_root()),
                                         title="选择要同步的电脑文件夹")
        if chosen:
            self.state.set_root(chosen)
            self._refresh_dir_label()
            update_config(root=chosen)
            self.set_footer(f"本机文件夹已切换：{chosen}")

    def open_root(self) -> None:
        try:
            path = str(self.state.get_root())
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # noqa: BLE001
            self.set_footer(f"打不开：{exc}")

    def copy_address(self) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.addr_label.cget("text"))
            self.set_footer("地址已复制，可在手机端「手动连接」里粘贴")
        except Exception:
            pass

    # ------------------------------------------------------------ 交互
    def set_mode(self, key: str) -> None:
        if key not in MODE_COLORS:
            return
        self.mode = key
        self._paint_mode()
        self.progress.set_colors(MODE_COLORS[key])
        update_config(mode=key)
        self.set_footer(f"{mode_label(key)}：{MODE_DESC[key]}")

    def _paint_mode(self) -> None:
        for key, tile in self._tiles.items():
            tile.set_selected(key == self.mode)
        if hasattr(self, "btn_sync"):
            self.btn_sync.set_colors(MODE_COLORS[self.mode])

    def _on_option(self, _value: bool) -> None:
        update_config(mirror_delete=self.cb_delete.value,
                      include_hidden=self.cb_hidden.value)
        self.set_footer("选项已保存")

    def _on_discover_mode(self, value: bool) -> None:
        self.state.discover_mode = "wifi" if value else "auto"
        update_config(discover_mode=self.state.discover_mode)
        self.set_footer("找设备方式：只从 WiFi 网卡广播" if value
                        else "找设备方式：所有网卡都广播")

    def current_peer(self) -> dict | None:
        for peer in self.peers:
            if peer["id"] == self.selected_peer_id:
                return peer
        return None

    def select_peer(self, pid: str) -> None:
        self.selected_peer_id = pid
        update_config(peer_id=pid)
        self._render_peers(force=True)
        peer = self.current_peer()
        if peer:
            self.set_footer(f"已选择 {peer['name']} · {peer['ip']}:{peer['port']}")

    def scan_lan(self) -> None:
        """广播被路由器 / 防火墙拦掉时，直接扫网段上的 37131 端口找手机。"""
        if getattr(self, "_scanning", False):
            return
        self._scanning = True
        self.btn_scan.set_enabled(False)
        self.btn_scan.set_text("扫描中…")
        self.set_footer("正在扫描当前网段找手机，约 3~8 秒…")

        def work() -> None:
            hits: list[dict] = []
            try:
                hits = lanscan.scan()
            except Exception as exc:  # noqa: BLE001
                self.state.events.put(("warn", {"text": f"扫描失败：{exc}"}))
            finally:
                self._scanning = False
            for hit in hits:
                self.state.note_peer(hit["ip"], {
                    "name": hit["name"],
                    "id": hit["id"],
                    "port": hit["port"],
                    "root": hit.get("root", ""),
                })
            self.state.events.put(("scan", {"count": len(hits)}))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ 手机列表
    def _refresh_peers(self) -> None:
        peers = self.state.peers_online()
        self.peers = peers
        sig = tuple((p["id"], p["name"], p["ip"], p["port"], p["root"]) for p in peers)
        if sig != self._peer_sig:
            self._peer_sig = sig
            self._render_peers()
        self.peer_badge.configure(text=f"{len(peers)} 台")

        known = {p["id"] for p in peers}
        if peers and (not self.selected_peer_id or (
                self.selected_peer_id not in known and len(peers) == 1)):
            self.selected_peer_id = peers[0]["id"]
            update_config(peer_id=peers[0]["id"])
            self._render_peers(force=True)

        online = bool(peers)
        name = ""
        if len(peers) == 1:
            name = peers[0]["name"]
        text = f"已连接 · {name}" if name else (f"已连接 · {len(peers)} 台手机" if peers else "等待手机连接")
        if text != self._last_status:
            self._last_status = text
            self.status_label.configure(text=text, fg=OK if online else WARN)
            self.status_dot.delete("all")
            dot(self.status_dot, 5, 5, OK if online else WARN)

        peer = self.current_peer()
        if peer:
            root = peer.get("root") or ""
            self.remote_label.configure(text=short_path(root, 36) if root else "手机上还没选文件夹")
            self.remote_hint.configure(text=f"{peer['name']} · {peer['ip']}:{peer['port']}")
        elif peers:
            self.remote_label.configure(text="上面选一台手机")
            self.remote_hint.configure(text="有多台手机时，点一台作为同步对象")
        else:
            self.remote_label.configure(text="连上手机后显示")
            self.remote_hint.configure(text="手机上可以随时换一个文件夹")

        if not peers:
            self._nudge_footer()

    def _nudge_footer(self) -> None:
        """没连上时给出能定位问题的提示，而不是干等着。"""
        ip = self.state.last_discover_ip
        fresh = bool(ip) and (time.time() - self.state.last_discover_at) < 8
        if fresh:
            text = f"收到 {ip} 的广播但握手没成功 —— 多半是防火墙拦了 TCP {self.port}"
        elif netinfo.wireless_down() and not [n for n in netinfo.nics() if n.wireless]:
            text = "无线网卡未连接 WiFi：手机走 WiFi 的话，两边不在同一个网络"
        else:
            text = ""
        if text and text != self._nudge:
            self._nudge = text
            self.set_footer(text)
        elif not text:
            self._nudge = ""

    def _render_peers(self, force: bool = False) -> None:
        for child in self.peer_box.winfo_children():
            child.destroy()

        if not self.peers:
            tk.Label(self.peer_box, text="等待手机连接…  同一 WiFi 打开 SynSimplify App",
                     bg=PANEL, fg=MUTED, font=(self.font, 9), anchor="w").pack(
                fill="x", padx=6, pady=6)
            return

        for peer in self.peers[:4]:
            selected = peer["id"] == self.selected_peer_id
            bg = mix_bg(ACCENT, 0.15, CARD2) if selected else CARD2
            border = blend(STROKE, ACCENT, 0.55) if selected else STROKE
            row = tk.Frame(self.peer_box, bg=bg, highlightbackground=border,
                           highlightthickness=1, cursor="hand2")
            row.pack(fill="x", pady=(0, 4))

            avatar = Avatar(row, peer["name"], peer.get("hue") or 210, 30, bg)
            avatar.pack(side="left", padx=(8, 9), pady=7)

            col = tk.Frame(row, bg=bg)
            col.pack(side="left", fill="x", expand=True, pady=6)
            name = tk.Label(col, text=peer["name"], bg=bg, fg=TEXT,
                            font=(self.font, 9, "bold"), anchor="w")
            name.pack(fill="x")
            sub = tk.Label(col, text=f"{peer['ip']}:{peer['port']} · {short_path(peer.get('root', '') or '未选文件夹', 30)}",
                           bg=bg, fg=MUTED, font=(self.font, 8), anchor="w")
            sub.pack(fill="x")

            state_text = "同步对象" if selected else "选这台"
            tag = tk.Label(row, text=state_text, bg=bg, fg=ACCENT if selected else SUB,
                           font=(self.font, 8, "bold" if selected else "normal"))
            tag.pack(side="right", padx=10)

            pid = peer["id"]
            for widget in (row, avatar, col, name, sub, tag):
                widget.bind("<Button-1>", lambda e, v=pid: self.select_peer(v))

    # ------------------------------------------------------------ 同步
    def start_sync(self, dry: bool = False) -> None:
        if self.running:
            return
        peer = self.current_peer()
        if peer is None:
            self.set_footer("先等手机连上，或在上方选中一台手机")
            return
        if not peer.get("port"):
            self.set_footer("这台手机没有报告同步端口，请把 App 重新打开一次")
            return

        self.running = True
        self.dry_run = dry
        self.counts = {"up": 0, "down": 0, "skip": 0, "fail": 0}
        self.plan_iids.clear()
        self.total_bytes = 0
        self.done_bytes = 0
        self.cur_rel = ""
        self.cur_done = 0
        self.cur_total = 0
        self._started_at = time.perf_counter()
        self._clear_tree()
        self._empty_hint.place_forget()
        self.progress.set_value(0)
        self.file_label.configure(text="正在读取手机文件列表…")
        self.bytes_label.configure(text="")
        for key in ("up", "down", "skip", "spend"):
            self.stat_labels[key].configure(text="—")

        self.btn_sync.set_enabled(False)
        self.btn_sync.set_text("预览中…" if dry else "同步中…")
        self.btn_preview.set_enabled(False) if hasattr(self.btn_preview, "set_enabled") else None
        self.btn_stop.grid()
        self.plan_badge.configure(text="准备中", fg=WARN, bg=mix_bg(WARN, 0.14, PANEL))

        self.state.reset_sync(self.mode)
        self.state.cancel.clear()

        client = PeerClient(peer["ip"], peer["port"])
        client.device_name = self.state.name or socket.gethostname()
        client.device_id = self.state.host_id
        runner = SyncRunner(
            client, self.state.get_root(), peer.get("root", ""), self.mode,
            mirror_delete=self.cb_delete.value, include_hidden=self.cb_hidden.value,
            on_event=lambda kind, payload: self.state.events.put((kind, payload)),
            cancel=self.state.cancel, dry_run=dry,
        )

        def work() -> None:
            try:
                runner.run()
            except Exception as exc:  # noqa: BLE001
                self.state.events.put(("fatal", {"text": f"{type(exc).__name__}: {exc}"}))
            finally:
                client.close()

        threading.Thread(target=work, daemon=True).start()

    def stop_sync(self) -> None:
        if self.running:
            self.state.cancel.set()
            self.set_footer("正在停止…")

    def _clear_tree(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)

    def _reset_buttons(self) -> None:
        self.running = False
        self.btn_sync.set_enabled(True)
        self.btn_sync.set_text("立即同步")
        self.btn_sync.set_colors(MODE_COLORS[self.mode])
        if hasattr(self.btn_preview, "set_enabled"):
            self.btn_preview.set_enabled(True)
        self.btn_stop.grid_remove()

    # ------------------------------------------------------------ 事件
    def _on_op_row(self, op: dict, index: int) -> str:
        kind = op["op"]
        label, tag = {
            "push": ("↓ 到手机", "push"),
            "pull": ("↑ 到电脑", "pull"),
            "mkdir_remote": ("目录", "dir"),
            "mkdir_local": ("目录", "dir"),
            "del_remote": ("删除手机", "del"),
            "del_local": ("删除电脑", "del"),
            "skip": ("跳过", "skip"),
            "same": ("已相同", "same"),
        }.get(kind, (kind, "same"))
        state_text = op.get("why", "")
        if kind in ("push", "pull"):
            state_text = "待传输"
        size = human_size(op.get("s", 0)) if kind in ("push", "pull") else ""
        iid = str(index)
        self.tree.insert("", "end", iid=iid,
                         values=(label, op.get("p", ""), size, state_text), tags=(tag,))
        return iid

    def _handle_event(self, kind: str, payload: dict) -> None:
        if kind == "phase":
            self.file_label.configure(text=short_path(payload.get("text", ""), 60))
        elif kind == "warn":
            self.set_footer(payload.get("text", ""))
        elif kind == "info":
            self.set_footer(payload.get("text", ""))
        elif kind == "scan":
            self.btn_scan.set_text("扫描本网络")
            self.btn_scan.set_enabled(True)
            self._refresh_peers()
            count = int(payload.get("count", 0) or 0)
            self.set_footer(f"扫描完成：找到 {count} 台手机" if count else
                            "没扫到手机：确认手机也连着同一个路由器，或换个网段再试")
        elif kind == "peer":
            self.remote_label.configure(text=short_path(payload.get("root", ""), 36))
        elif kind == "plan":
            self._apply_plan(payload.get("ops", []))
        elif kind == "op_start":
            self._apply_op_start(payload)
        elif kind == "op_progress":
            self._apply_op_progress(payload)
        elif kind == "op_done":
            self._apply_op_done(payload)
        elif kind == "op_fail":
            self._apply_op_fail(payload)
        elif kind == "finish":
            self._apply_finish(payload)
        elif kind == "fatal":
            self.set_footer(f"同步失败：{payload.get('text', '')}")
            self._reset_buttons()
            self.state.set_status("error")
        elif kind == "root":
            self._refresh_dir_label()

    def _apply_plan(self, ops: list[dict]) -> None:
        self._clear_tree()
        self.plan_iids.clear()
        self.done_bytes = 0
        self.total_bytes = sum(op.get("s", 0) for op in ops if op["op"] in ("push", "pull"))
        moved = [op for op in ops if op["op"] in ("push", "pull")]
        visible = [op for op in ops if op["op"] != "same"]
        for index, op in enumerate(visible[:MAX_ROWS]):
            iid = self._on_op_row(op, index)
            self.plan_iids[op["p"]] = iid
        todo = len([o for o in ops if o["op"] not in ("same", "skip")])
        self.plan_badge.configure(
            text=f"{todo} 项 · {human_size(self.total_bytes)}" if todo else "无需同步",
            fg=MINT if todo else OK, bg=mix_bg(MINT if todo else OK, 0.14, PANEL))
        self.file_label.configure(
            text=f"计划：{len(moved)} 个文件 · {human_size(self.total_bytes)} · "
                 f"跳过 {len(ops) - len(moved)}")
        if self.dry_run:
            self.set_footer("这是预览，没有动任何文件；确认后点「立即同步」")
        if visible:
            self._empty_hint.place_forget()
            self.tree.see("0")
        else:
            self._empty_hint.configure(text="两边完全一致，没有需要同步的文件")
            self._empty_hint.place(relx=0.5, rely=0.56, anchor="center")

    def _apply_op_start(self, op: dict) -> None:
        iid = self.plan_iids.get(op.get("p", ""))
        if iid is None:
            return
        kind = op["op"]
        label = {"push": "↓ 到手机", "pull": "↑ 到电脑",
                 "del_remote": "删除手机", "del_local": "删除电脑",
                 "mkdir_remote": "目录", "mkdir_local": "目录"}.get(kind, kind)
        size = human_size(op.get("s", 0)) if kind in ("push", "pull") else ""
        self.tree.item(iid, values=(label, op.get("p", ""), size, "传输中 0%"))
        self.cur_rel = op.get("p", "")
        self.cur_done = 0
        self.cur_total = int(op.get("s", 0))
        self.file_label.configure(text=short_path(self.cur_rel, 60))
        try:
            self.tree.see(iid)
        except tk.TclError:
            pass

    def _apply_op_progress(self, payload: dict) -> None:
        rel = payload.get("p", "")
        if rel != self.cur_rel:
            return
        done = int(payload.get("done", 0))
        total = int(payload.get("total", 0)) or self.cur_total
        self.cur_done = done
        self.cur_total = total
        pct = int(done * 100 / total) if total else 0
        iid = self.plan_iids.get(rel)
        if iid is not None:
            values = list(self.tree.item(iid, "values"))
            if len(values) == 4:
                values[3] = f"传输中 {pct}%"
                self.tree.item(iid, values=values)
        self._paint_progress()

    def _apply_op_done(self, payload: dict) -> None:
        rel = payload.get("p", "")
        iid = self.plan_iids.get(rel)
        kind = payload.get("op", "")
        ms = payload.get("ms", 0)
        if kind == "push":
            self.counts["up"] += 1
        elif kind == "pull":
            self.counts["down"] += 1
        elif kind == "skip":
            self.counts["skip"] += 1
        if iid is not None:
            values = list(self.tree.item(iid, "values"))
            if len(values) == 4:
                if kind in ("push", "pull"):
                    values[3] = f"完成 · {ms:.0f} ms"
                elif kind in ("del_remote", "del_local"):
                    values[3] = "已删除"
                elif kind == "mkdir_remote":
                    values[3] = "已创建（手机）"
                elif kind == "mkdir_local":
                    values[3] = "已创建（电脑）"
                elif kind == "skip":
                    values[3] = payload.get("why") or "跳过"
                self.tree.item(iid, values=values, tags=("done",))
        if kind in ("push", "pull"):
            self.done_bytes += int(payload.get("bytes", 0) or 0)
            self.cur_done = self.cur_total
        self._paint_progress()
        self._paint_stats()

    def _apply_op_fail(self, payload: dict) -> None:
        self.counts["fail"] += 1
        rel = payload.get("p", "")
        iid = self.plan_iids.get(rel)
        if iid is not None:
            values = list(self.tree.item(iid, "values"))
            if len(values) == 4:
                values[3] = "失败：" + str(payload.get("error", ""))[:60]
                self.tree.item(iid, values=values, tags=("fail",))
        self.set_footer(f"{rel} 失败：{payload.get('error', '')}")
        self._paint_stats()

    def _apply_finish(self, payload: dict) -> None:
        stats = payload.get("stats", {})
        self._finish_stats = stats
        self._reset_buttons()
        elapsed = float(stats.get("elapsed", 0))
        self.done_bytes = int(stats.get("up_bytes", 0)) + int(stats.get("down_bytes", 0))
        self.cur_total = 0
        self.cur_done = 0
        ratio = (self.done_bytes / self.total_bytes) if self.total_bytes else 1.0
        self.progress.set_value(max(0.0, min(1.0, ratio)))
        self.counts["up"] = int(stats.get("up_files", 0))
        self.counts["down"] = int(stats.get("down_files", 0))
        self.counts["skip"] = int(stats.get("skip", 0))
        self.counts["fail"] = int(stats.get("fail", 0))
        self._paint_stats()
        self._paint_progress()

        up = self.counts["up"]
        down = self.counts["down"]
        fail = self.counts["fail"]
        speed = float(stats.get("speed", 0))
        if payload.get("dry"):
            self.file_label.configure(text="预览完成，没有改动任何文件")
            self.plan_badge.configure(text="预览", fg=WARN, bg=mix_bg(WARN, 0.14, PANEL))
            self.set_footer("预览完成：确认方向没问题再点「立即同步」")
        else:
            text = f"完成 · 上行 {up} · 下行 {down}"
            if fail:
                text += f" · 失败 {fail}"
            self.file_label.configure(text=text)
            self.plan_badge.configure(
                text="同步完成" if not fail else "部分失败",
                fg=OK if not fail else ERR,
                bg=mix_bg(OK if not fail else ERR, 0.14, PANEL))
            self.set_footer(
                f"{text} · 用时 {elapsed:.1f}s · 平均 {speed:.1f} MB/s")
        self.state.set_status("done" if not fail else "error")

    def _paint_progress(self) -> None:
        done = self.done_bytes + (self.cur_done if self.cur_total else 0)
        total = self.total_bytes
        ratio = (done / total) if total else (0.0 if self.running else 1.0)
        self.progress.set_value(max(0.0, min(1.0, ratio)))
        spent = max(0.001, time.perf_counter() - self._started_at) if self.running else 0.0
        speed = (done / 1024 / 1024) / spent if spent else 0.0
        bits = []
        if total:
            bits.append(f"{human_size(done)} / {human_size(total)}")
        if self.running and speed > 0.05:
            bits.append(f"{speed:.1f} MB/s")
        self.bytes_label.configure(text=" · ".join(bits))

    def _paint_stats(self) -> None:
        spent = time.perf_counter() - self._started_at if self._started_at else 0.0
        self.stat_labels["up"].configure(text=str(self.counts["up"]))
        self.stat_labels["down"].configure(text=str(self.counts["down"]))
        self.stat_labels["skip"].configure(text=str(self.counts["skip"]))
        self.stat_labels["spend"].configure(text=f"{spent:.0f}s" if spent else "—")

    # ------------------------------------------------------------ 轮询
    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.state.events.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass

        self._refresh_peers()
        if self.running:
            self._paint_progress()
        self.root.after(150, self._poll)

    def run(self) -> None:
        self.root.mainloop()
