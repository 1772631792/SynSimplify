# -*- coding: utf-8 -*-
"""不依赖广播地找手机：直接扫当前网段上的 37131~37142 端口。

UDP 广播会被路由器（AP 隔离）、Windows 防火墙、多网卡路由中的任意一环掐掉，
但手机端一直在 0.0.0.0:37131 上开着 HTTP 服务。只要两边真的在同一个二层网络里，
主动 TCP 连一下就一定连得上 —— 所以这条路比广播可靠，只是慢一点（几秒）。
"""

from __future__ import annotations

import json
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import netinfo

PHONE_PORTS = tuple(range(37131, 37143))
CONNECT_TIMEOUT = 0.28


def _probe(ip: str, port: int) -> dict | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(CONNECT_TIMEOUT)
    try:
        sock.connect((ip, port))
    except OSError:
        return None
    finally:
        sock.close()

    info: dict = {}
    try:
        req = urllib.request.Request(f"http://{ip}:{port}/syn/info",
                                     headers={"User-Agent": "SynSimplifyHost"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            info = json.loads(resp.read().decode("utf-8", "ignore") or "{}")
    except Exception:  # noqa: BLE001 - 端口开着但不是我们的人，或读取超时
        info = {}

    return {
        "id": str(info.get("id") or ip),
        "ip": ip,
        "port": port,
        "name": str(info.get("name") or "手机"),
        "root": str(info.get("root") or ""),
        "app": str(info.get("app") or ""),
        "verified": bool(info.get("id")),
    }


def hosts_in(nic: netinfo.Nic, limit: int = 254) -> list[str]:
    """按 /24 猜同网段的其它主机地址。"""
    parts = nic.ip.split(".")
    if len(parts) != 4:
        return []
    head = ".".join(parts[:3])
    return [f"{head}.{i}" for i in range(1, limit + 1) if f"{head}.{i}" != nic.ip]


def scan(on_log=None, timeout: float = 6.0) -> list[dict]:
    """扫所有启用网卡的 /24，返回找到的手机（已按 ip 去重）。"""
    targets: list[str] = []
    for nic in netinfo.nics():
        for ip in hosts_in(nic):
            if ip not in targets:
                targets.append(ip)
    if not targets:
        return []

    found: list[dict] = []
    seen: set[str] = set()

    def work(ip: str) -> None:
        for port in PHONE_PORTS[:3]:      # 手机一般就用 37131，先试前三个
            hit = _probe(ip, port)
            if hit and hit["verified"] and hit["ip"] not in seen:
                seen.add(hit["ip"])
                found.append(hit)
                if on_log:
                    on_log(f"找到 {hit['name']} {hit['ip']}:{hit['port']}")
                return

    with ThreadPoolExecutor(max_workers=96) as pool:
        list(pool.map(work, targets))
    found.sort(key=lambda d: d["ip"])
    return found


if __name__ == "__main__":  # pragma: no cover - 手动排查用
    for n in netinfo.nics():
        print(f"网卡 {n.label()}")
    if not netinfo.wireless_down():
        pass
    print("扫描中，最多几秒 …")
    hits = scan(print)
    print(json.dumps(hits, ensure_ascii=False, indent=2) if hits else "没找到手机")
