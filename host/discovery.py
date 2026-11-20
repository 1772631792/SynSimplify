# -*- coding: utf-8 -*-
"""UDP 广播发现：手机发 SYNSIMPLIFY/DISCOVER，电脑回一条 HOST。

手机每 0.6~1.5 秒发一次，所以电脑这边不需要主动广播：
收到包就知道有手机在线，回包里带上自己的地址、端口、文件夹。
"""

from __future__ import annotations

import json
import socket
import threading
import time

from config import APP_TAG, DISCOVERY_PORT, PROTO_VER
from state import HostState

DISCOVER = APP_TAG + "/DISCOVER"
HOST = APP_TAG + "/HOST"
BYE = APP_TAG + "/BYE"


def _parse(text: str) -> dict:
    _, _, raw = text.partition(" ")
    raw = raw.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def discovery_loop(state: HostState, stop: threading.Event) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", DISCOVERY_PORT))
    except OSError as exc:
        state.events.put(("warn", {"text": f"发现端口 {DISCOVERY_PORT} 打不开：{exc}（可在手机端手动填 IP）"}))
        sock.close()
        return

    sock.settimeout(1.0)
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            break

        text = data.decode("utf-8", "ignore").strip()
        if not text.startswith(APP_TAG):
            continue
        ip = addr[0]

        if text.startswith(BYE):
            info = _parse(text)
            pid = str(info.get("id") or ip)
            state.drop_peer(pid)
            state.events.put(("peers", {"count": len(state.peers_online())}))
            continue

        if not text.startswith(DISCOVER):
            continue

        incoming = _parse(text)
        state.note_peer(ip, incoming)

        snap = state.snapshot()
        reply = {
            "name": snap["name"],
            "id": snap["id"],
            "hue": snap["hue"],
            "port": state.port,
            "root": snap["root"],
            "ver": PROTO_VER,
            "busy": snap["status"] == "running",
            "t": int(time.time() * 1000),
        }
        payload = (HOST + " " + json.dumps(reply, ensure_ascii=False)).encode("utf-8")
        try:
            sock.sendto(payload, addr)
        except OSError:
            pass
    sock.close()
