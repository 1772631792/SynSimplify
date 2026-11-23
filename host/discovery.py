# -*- coding: utf-8 -*-
"""UDP 广播发现。

两个方向都要有：

* 被动：手机每 0.6~1.5 秒广播一次 SYNSIMPLIFY/DISCOVER，电脑收到后回一条 HOST。
* 主动：电脑自己定时往每张网卡广播 HOST（`beacon_loop`）。

为什么要有主动那一半：电脑同时插网线、又连着 WiFi 时，默认路由往往走网线，
手机发来的广播电脑不一定收得到，电脑回的包也可能从网线那张卡出去 —— 表现就是
「同一个 WiFi 却找不到设备」。主动广播是逐张网卡绑源地址发出去的，WiFi 那张
一定会带上，手机收到 HOST 就能反向连上电脑。`discover_mode = "wifi"` 时只走无线网卡。
"""

from __future__ import annotations

import json
import socket
import threading
import time

import netinfo
from config import APP_TAG, DISCOVERY_PORT, PROTO_VER
from state import HostState

DISCOVER = APP_TAG + "/DISCOVER"
HOST = APP_TAG + "/HOST"
BYE = APP_TAG + "/BYE"

BEACON_INTERVAL = 1.5      # 主动广播间隔（秒）


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


def host_payload(state: HostState) -> bytes:
    """电脑这边的自我介绍，被动回复和主动广播共用。"""
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
    return (HOST + " " + json.dumps(reply, ensure_ascii=False)).encode("utf-8")


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

        try:
            sock.sendto(host_payload(state), addr)
        except OSError:
            pass
    sock.close()


# ---------------------------------------------------------------- 主动广播
class _Beacon:
    """按网卡缓存发送 socket：绑定到该网卡 IP，广播就一定从那张卡出去。"""

    def __init__(self) -> None:
        self._socks: dict[str, socket.socket] = {}

    def socket_for(self, ip: str) -> socket.socket | None:
        sock = self._socks.get(ip)
        if sock is not None:
            return sock
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((ip, 0))
        except OSError:
            try:
                sock.close()
            except Exception:  # noqa: BLE001
                pass
            return None
        self._socks[ip] = sock
        return sock

    def send(self, payload: bytes, nic: netinfo.Nic, port: int) -> bool:
        sock = self.socket_for(nic.ip)
        if sock is None:
            return False
        ok = False
        # 受限广播 + 定向广播各来一次：有的路由器/AP 只放行其中一种
        for target in ("255.255.255.255", nic.subnet_broadcast):
            try:
                sock.sendto(payload, (target, port))
                ok = True
            except OSError:
                pass
        return ok

    def prune(self, alive: set[str]) -> None:
        for ip in list(self._socks):
            if ip in alive:
                continue
            try:
                self._socks.pop(ip).close()
            except Exception:  # noqa: BLE001
                pass

    def close(self) -> None:
        self.prune(set())


def beacon_loop(state: HostState, stop: threading.Event, interval: float = BEACON_INTERVAL,
                port: int = DISCOVERY_PORT) -> None:
    """电脑主动广播自己，让 WiFi 那侧的手机能反向发现这台机器。"""
    beacon = _Beacon()
    last_sig: tuple | None = None
    announced_none = False

    try:
        while not stop.is_set():
            mode = getattr(state, "discover_mode", "auto")
            prefer_wifi = mode == "wifi"
            available = netinfo.nics()
            wireless = [n for n in available if n.wireless]
            if prefer_wifi and wireless:
                candidates, note = wireless, "仅无线网卡"
            elif prefer_wifi:
                candidates, note = available, "没插无线网卡，先用全部网卡"
            else:
                candidates, note = available, "全部网卡"
            # 无线的排后面：包里的 IP 手机端后收到会覆盖前者，让 WiFi 地址成为最终值
            candidates.sort(key=lambda n: n.wireless)

            payload = host_payload(state)
            sent: list[str] = []
            for nic in candidates:
                if beacon.send(payload, nic, port):
                    sent.append(nic.label())
            beacon.prune({n.ip for n in candidates})

            sig = tuple(sent)
            if sig != last_sig:
                last_sig = sig
                if sent:
                    state.events.put(("info", {"text": f"主动广播（{note}）：{'、'.join(sent)}"}))
                    announced_none = False
                elif not announced_none:
                    announced_none = True
                    state.events.put(("warn", {"text": "没有可用的网卡用于主动广播，手机可能需要手动填 IP"}))

            stop.wait(interval)
    finally:
        beacon.close()
