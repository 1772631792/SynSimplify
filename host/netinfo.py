# -*- coding: utf-8 -*-
"""本机网络接口一览。

一台电脑同时插着网线、又连着 WiFi 时，「发出去的广播从哪张网卡走」由路由表决定，
默认往往走网线那一张，于是同一 WiFi 下的手机永远收不到。这里把所有启用的 IPv4
接口都列出来（并标出哪张是无线网卡），让发现模块挨个发一遍。
"""

from __future__ import annotations

import socket
import sys
from dataclasses import dataclass

IF_TYPE_IEEE80211 = 71        # Windows: 无线网卡
IF_OPER_STATUS_UP = 1


@dataclass(frozen=True)
class Nic:
    """一块网卡上的一个 IPv4 地址。"""

    ip: str
    name: str
    iftype: int = 0

    @property
    def wireless(self) -> bool:
        return self.iftype == IF_TYPE_IEEE80211

    @property
    def subnet_broadcast(self) -> str:
        """按 /24 猜一个定向广播地址，绝大多数家庭 / 办公网都是这个划分。"""
        parts = self.ip.split(".")
        if len(parts) != 4:
            return "255.255.255.255"
        return ".".join(parts[:3] + ["255"])

    def label(self) -> str:
        kind = "WiFi" if self.wireless else "有线"
        return f"{self.name or kind}({self.ip})"


def _is_usable(ip: str) -> bool:
    return bool(ip) and not ip.startswith("127.") and not ip.startswith("169.254.") and ip != "0.0.0.0"


# ----------------------------------------------------------------- windows
def _windows_nics() -> list[Nic]:
    import ctypes
    from ctypes import wintypes

    class SOCKADDR(ctypes.Structure):
        _fields_ = [("sa_family", wintypes.USHORT), ("sa_data", ctypes.c_byte * 14)]

    class SOCKADDR_IN(ctypes.Structure):
        _fields_ = [
            ("sin_family", ctypes.c_short),
            ("sin_port", ctypes.c_ushort),
            ("sin_addr", ctypes.c_ubyte * 4),
            ("sin_zero", ctypes.c_byte * 8),
        ]

    class SOCKET_ADDRESS(ctypes.Structure):
        _fields_ = [
            ("lpSockaddr", ctypes.POINTER(SOCKADDR)),
            ("iSockaddrLength", ctypes.c_int),
        ]

    class UNICAST(ctypes.Structure):
        pass

    UNICAST._fields_ = [
        ("Length", wintypes.ULONG),
        ("Flags", wintypes.DWORD),
        ("Next", ctypes.POINTER(UNICAST)),
        ("Address", SOCKET_ADDRESS),
    ]

    class ADAPTER(ctypes.Structure):
        pass

    # 只声明到 OperStatus 为止，后面的字段用不到
    ADAPTER._fields_ = [
        ("Length", wintypes.ULONG),
        ("IfIndex", wintypes.DWORD),
        ("Next", ctypes.POINTER(ADAPTER)),
        ("AdapterName", ctypes.c_char_p),
        ("FirstUnicastAddress", ctypes.POINTER(UNICAST)),
        ("FirstAnycastAddress", ctypes.c_void_p),
        ("FirstMulticastAddress", ctypes.c_void_p),
        ("FirstDnsServerAddress", ctypes.c_void_p),
        ("DnsSuffix", ctypes.c_wchar_p),
        ("Description", ctypes.c_wchar_p),
        ("FriendlyName", ctypes.c_wchar_p),
        ("PhysicalAddress", ctypes.c_ubyte * 8),
        ("PhysicalAddressLength", wintypes.ULONG),
        ("Flags", wintypes.ULONG),
        ("Mtu", wintypes.ULONG),
        ("IfType", wintypes.ULONG),
        ("OperStatus", ctypes.c_int),
    ]

    AF_INET = 2
    GAA_FLAGS = 0x0002 | 0x0004 | 0x0008      # 跳过 anycast / multicast / DNS
    ERROR_BUFFER_OVERFLOW = 111

    iphlpapi = ctypes.WinDLL("iphlpapi.dll")
    iphlpapi.GetAdaptersAddresses.argtypes = [
        wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p,
        ctypes.POINTER(ADAPTER), ctypes.POINTER(wintypes.ULONG),
    ]
    iphlpapi.GetAdaptersAddresses.restype = wintypes.ULONG

    size = wintypes.ULONG(16 * 1024)
    for _ in range(4):
        buf = ctypes.create_string_buffer(size.value)
        head = ctypes.cast(buf, ctypes.POINTER(ADAPTER))
        ret = iphlpapi.GetAdaptersAddresses(AF_INET, GAA_FLAGS, None, head, ctypes.byref(size))
        if ret == ERROR_BUFFER_OVERFLOW:
            continue
        if ret != 0:
            raise OSError(f"GetAdaptersAddresses -> {ret}")
        break
    else:
        return []

    out: list[Nic] = []
    seen: set[str] = set()
    node = head
    while node:
        adapter = node.contents
        node = adapter.Next
        if adapter.OperStatus != IF_OPER_STATUS_UP:
            continue
        name = adapter.FriendlyName or adapter.Description or ""
        u = adapter.FirstUnicastAddress
        while u:
            item = u.contents
            u = item.Next
            addr = item.Address.lpSockaddr
            if not addr:
                continue
            if addr.contents.sa_family != AF_INET:
                continue
            sin = ctypes.cast(addr, ctypes.POINTER(SOCKADDR_IN)).contents
            ip = socket.inet_ntoa(bytes(bytearray(sin.sin_addr)))
            if not _is_usable(ip) or ip in seen:
                continue
            seen.add(ip)
            out.append(Nic(ip=ip, name=name, iftype=int(adapter.IfType)))
    return out


# ----------------------------------------------------------------- 其它系统
def _fallback_nics() -> list[Nic]:
    out: list[Nic] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if _is_usable(ip) and ip not in {n.ip for n in out}:
                out.append(Nic(ip=ip, name=hostname))
    except OSError:
        pass
    return out


_VIRTUAL_HINTS = (
    "tailscale", "zerotier", "vmware", "virtualbox", "hyper-v", "vethernet",
    "wsl", "docker", "loopback", "tap-", "tun", "npcap",
)


def _looks_virtual(nic: Nic) -> bool:
    name = (nic.name or "").lower()
    return any(hint in name for hint in _VIRTUAL_HINTS)


def nics() -> list[Nic]:
    """当前启用的 IPv4 网卡（Windows 上带无线标识，虚拟网卡会被剔掉）。"""
    out: list[Nic] = []
    if sys.platform == "win32":
        try:
            out = _windows_nics()
        except Exception:  # noqa: BLE001 - 拿不到就走兜底，不要影响启动
            out = []
    else:
        out = _fallback_nics()

    physical = [n for n in out if not _looks_virtual(n)]
    return physical or out


if __name__ == "__main__":  # pragma: no cover - 手动排查用
    for nic in nics():
        print(f"{nic.ip:16} {'WiFi' if nic.wireless else '有线':4} {nic.name}")
