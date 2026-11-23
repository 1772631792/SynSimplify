# -*- coding: utf-8 -*-
"""运行期状态：同步根目录、找到的手机、同步进度与事件队列。"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from config import HTTP_PORT, hue_from_id

ONLINE_WINDOW = 25.0


class HostState:
    def __init__(self, root: Path, host_id: str = "synsimplify", name: str = ""):
        self._lock = threading.Lock()
        self._root = Path(root)
        self.port = HTTP_PORT
        self.host_id = host_id
        self.name = name
        self.hue = hue_from_id(host_id)
        self.events: "queue.Queue[tuple[str, dict]]" = queue.Queue()
        self.peers: dict[str, dict] = {}
        # auto：所有网卡都广播；wifi：只从无线网卡广播（同时插网线时用）
        self.discover_mode = "auto"
        # 最近一次收到手机广播的来源，用来区分「广播没到」和「广播到了但连不上」
        self.last_discover_ip = ""
        self.last_discover_at = 0.0
        self.sync_status = "idle"        # idle / scanning / running / done / error / stopped
        self.sync_mode = "push"
        self.sync_stats: dict = {}
        self.plan_ops: list[dict] = []
        self.remote_info: dict = {}
        self.cancel = threading.Event()
        self._ensure_root()

    # ---------------------------------------------------------------- 目录
    def _ensure_root(self) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def get_root(self) -> Path:
        with self._lock:
            return self._root

    def set_root(self, path: str | Path) -> None:
        with self._lock:
            self._root = Path(path)
        self._ensure_root()
        self.events.put(("root", {"root": str(path)}))

    # ---------------------------------------------------------------- 手机
    def note_peer(self, ip: str, info: dict | None = None) -> dict:
        info = info or {}
        pid = str(info.get("id") or ip or "phone")
        with self._lock:
            peer = self.peers.setdefault(pid, {
                "id": pid, "ip": ip, "name": "手机", "port": 0, "root": "", "hue": 0,
                "last_seen": 0.0, "app": "",
            })
            if ip:
                peer["ip"] = ip
            for key in ("name", "root", "app"):
                if info.get(key):
                    peer[key] = str(info[key])
            if info.get("port"):
                peer["port"] = int(info["port"])
            if info.get("hue") is not None:
                peer["hue"] = int(info["hue"])
            if not peer.get("hue"):
                peer["hue"] = hue_from_id(pid)
            peer["last_seen"] = time.time()
            peer["port"] = peer.get("port") or 37131
            return dict(peer)

    def peers_online(self) -> list[dict]:
        now = time.time()
        with self._lock:
            alive = [dict(p) for p in self.peers.values() if now - p["last_seen"] < ONLINE_WINDOW]
        alive.sort(key=lambda p: p["name"].lower())
        return alive

    def peer(self, pid: str) -> dict | None:
        with self._lock:
            p = self.peers.get(pid)
            return dict(p) if p else None

    def drop_peer(self, pid: str) -> None:
        with self._lock:
            self.peers.pop(pid, None)

    # ---------------------------------------------------------------- 同步
    def reset_sync(self, mode: str = "push") -> None:
        with self._lock:
            self.sync_status = "scanning"
            self.sync_mode = mode
            self.sync_stats = {}
            self.plan_ops = []
        self.cancel.clear()
        self.events.put(("status", {"status": "scanning"}))

    def set_plan(self, ops: list[dict], stats: dict) -> None:
        with self._lock:
            self.plan_ops = ops
            self.sync_stats = dict(stats)
            self.sync_status = "running"
        self.events.put(("status", {"status": "running"}))

    def set_status(self, status: str) -> None:
        with self._lock:
            self.sync_status = status
        self.events.put(("status", {"status": status}))

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.host_id,
                "name": self.name,
                "hue": self.hue,
                "port": self.port,
                "root": str(self._root),
                "status": self.sync_status,
                "mode": self.sync_mode,
                "stats": dict(self.sync_stats),
                "ops": list(self.plan_ops),
                "remote": dict(self.remote_info),
            }
