# -*- coding: utf-8 -*-
"""常量、本地配置与几个小工具。"""

from __future__ import annotations

import json
import socket
import time
import uuid
from pathlib import Path

APP_NAME = "SynSimplify"
APP_VER = "1.0.2"

DISCOVERY_PORT = 37120
HTTP_PORT = 37121
PORT_SPAN = 20
APP_TAG = "SYNSIMPLIFY"
PROTO_VER = 1

# 一次扫描最多收多少条，防止误选 C:\ 这种目录把手机内存打爆
MAX_SCAN = 40000

CONFIG_PATH = Path.home() / ".synsimplify_host.json"

MODE_PUSH = "push"      # 电脑 → 手机
MODE_PULL = "pull"      # 手机 → 电脑
MODE_TWO = "two"        # 双向
MODES = (MODE_PUSH, MODE_PULL, MODE_TWO)


def default_root() -> Path:
    """默认同步文件夹：家里一个干净的 SynSimplify，避免第一次就同步整个用户目录。"""
    home = Path.home()
    base = home / "Documents" if (home / "Documents").exists() else home
    return base / "SynSimplify"


def _default_config() -> dict:
    return {
        "root": str(default_root()),
        "port": HTTP_PORT,
        "id": uuid.uuid4().hex[:8],
        "name": socket.gethostname(),
        "mode": MODE_PUSH,
        "mirror_delete": False,
        "include_hidden": False,
        "peer_id": "",
        "discover_mode": "auto",     # auto：所有网卡；wifi：只从无线网卡找设备
    }


def load_config() -> dict:
    cfg = _default_config()
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in cfg})
    except Exception:
        pass
    if not cfg.get("id"):
        cfg["id"] = uuid.uuid4().hex[:8]
    return cfg


def save_config(cfg: dict) -> None:
    try:
        current = load_config()
        current.update(cfg)
        CONFIG_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def update_config(**changes) -> dict:
    cfg = load_config()
    cfg.update(changes)
    save_config(cfg)
    return cfg


def hue_from_id(value: str) -> int:
    """同一个 id 永远得到同一个色相，头像颜色就稳定了。"""
    total = sum(ord(ch) * (i + 7) for i, ch in enumerate(value or "synsimplify"))
    return total % 360


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def now_ms() -> int:
    return int(time.time() * 1000)


def human_size(n: float) -> str:
    n = float(n)
    if n >= 1024 * 1024 * 1024:
        return f"{n / 1024 / 1024 / 1024:.2f} GB"
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n:.0f} B"


def short_path(path: str, limit: int = 46) -> str:
    return path if len(path) <= limit else path[:18] + " … " + path[-24:]


def mode_label(mode: str) -> str:
    return {MODE_PUSH: "电脑 → 手机", MODE_PULL: "手机 → 电脑", MODE_TWO: "双向同步"}.get(
        mode, "电脑 → 手机")
