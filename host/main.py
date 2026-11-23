#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SynSimplify 电脑端：同一 WiFi，电脑和手机双向同步文件夹。

用法：
    python main.py                         打开图形界面
    python main.py --no-gui                只跑服务（看日志）
    python main.py --sync 192.168.1.8:37131 --mode push   命令行直接同步一次
    python main.py --selftest              自检：起两套服务互相同步，跑完退出
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

from config import (
    APP_NAME,
    APP_VER,
    DISCOVERY_PORT,
    HTTP_PORT,
    MODE_PULL,
    MODE_PUSH,
    MODE_TWO,
    PROTO_VER,
    default_root,
    human_size,
    load_config,
)
import lanscan
import netinfo
from discovery import beacon_loop, discovery_loop
from server import start_http
from state import HostState
from sync import PeerClient, SyncRunner


# ------------------------------------------------------------------ 无界面
def _run_sync_cli(target: str, state: HostState, mode: str, mirror_delete: bool,
                  include_hidden: bool) -> int:
    host, _, port = target.replace("http://", "").partition(":")
    if not host:
        print("[x] 地址格式：192.168.1.8:37131")
        return 2
    client = PeerClient(host, int(port or 37131))
    client.device_name = state.name
    client.device_id = state.host_id

    def on_event(kind: str, payload: dict) -> None:
        if kind == "op_done":
            print(f"[+] {payload.get('op')}  {payload.get('p')}")
        elif kind == "op_fail":
            print(f"[x] {payload.get('p')}  {payload.get('error')}")
        elif kind == "phase":
            print(f"[.] {payload.get('text')}")

    try:
        info = client.info()
        print(f"[+] 对端：{info.get('name')} · {info.get('root')}")
        runner = SyncRunner(client, state.get_root(), info.get("root", ""), mode,
                            mirror_delete, include_hidden, on_event=on_event)
        stats = runner.run()
    except Exception as exc:  # noqa: BLE001
        print(f"[x] 同步失败：{type(exc).__name__}: {exc}")
        return 1
    finally:
        client.close()

    print(f"[+] 上行 {stats['up_files']} 个 / {human_size(stats['up_bytes'])}，"
          f"下行 {stats['down_files']} 个 / {human_size(stats['down_bytes'])}，"
          f"失败 {stats['fail']}，用时 {stats['elapsed']:.2f}s")
    return 0 if stats["fail"] == 0 else 1


def run_headless(state: HostState, port: int, args) -> int:
    server = start_http(state, port)
    if server is None:
        print(f"[x] 端口 {port}~{port + 20} 都被占用了")
        return 1
    threading.Thread(target=discovery_loop, args=(state, threading.Event()), daemon=True).start()
    threading.Thread(target=beacon_loop, args=(state, threading.Event()), daemon=True).start()

    print(f"[+] {APP_NAME} v{APP_VER}")
    print(f"[+] 同步文件夹：{state.get_root()}")
    print(f"[+] 服务地址：0.0.0.0:{state.port}  发现端口：{DISCOVERY_PORT}")
    print(f"[+] 找设备方式：{'只走 WiFi' if state.discover_mode == 'wifi' else '所有网卡'}")
    print("[+] Ctrl+C 结束")

    if args.sync:
        code = _run_sync_cli(args.sync, state, args.mode, args.mirror_delete, args.hidden)
        server.shutdown()
        return code

    try:
        while True:
            time.sleep(0.4)
            while not state.events.empty():
                kind, payload = state.events.get()
                if kind == "warn":
                    print("[!]", payload.get("text", ""))
    except KeyboardInterrupt:
        print("\n[+] 已停止")
    finally:
        server.shutdown()
    return 0


# ------------------------------------------------------------------ 扫描
def run_scan() -> int:
    """广播不靠谱时的兜底：直接扫网段上的手机端口。"""
    print(f"[+] {APP_NAME} v{APP_VER} · 扫描当前网段")
    for nic in netinfo.nics():
        print(f"    网卡：{nic.label()}{'  (WiFi)' if nic.wireless else ''}")
    for adapter in netinfo.wireless_down():
        print(f"[!] {adapter.name} 未连接 WiFi，手机走 WiFi 的话连不到这台电脑")
    if not netinfo.nics():
        print("[x] 没有可用的 IPv4 网卡")
        return 1

    print("[+] 扫描中，最多几秒 …")
    hits = lanscan.scan(on_log=lambda text: print("    " + text))
    if not hits:
        print("[x] 没扫到手机：确认手机和电脑连的是同一个路由器（AP 隔离 / 访客网络会让两边互相看不见）")
        return 1
    for hit in hits:
        print(f"[ok] {hit['name']}  {hit['ip']}:{hit['port']}  {hit.get('root', '')}")
    print("[ok] 可以在手机端「设置」里手动填电脑 IP，或直接在电脑端点「立即同步」")
    return 0


# ------------------------------------------------------------------ 自检
def _write(path: Path, data: bytes, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _digest(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def run_selftest() -> int:
    base = Path(tempfile.mkdtemp(prefix="synsimplify_selftest_"))
    pc_root = base / "pc"
    phone_root = base / "phone"
    pc_root.mkdir(parents=True)
    phone_root.mkdir(parents=True)

    now = time.time()
    blob = os.urandom(320_000)
    _write(pc_root / "a.txt", b"hello from pc", now - 30)
    _write(pc_root / "sub" / "nested.docx", b"nested file", now - 20)
    _write(pc_root / "deep" / "x" / "y.bin", blob, now - 10)
    _write(pc_root / "shared.txt", b"same both sides", now - 5)
    _write(phone_root / "shared.txt", b"same both sides", now - 5)
    _write(phone_root / "note.md", b"from phone", now - 4)

    state_pc = HostState(pc_root, host_id="selftest-pc", name="SELFTEST-PC")
    state_phone = HostState(phone_root, host_id="selftest-phone", name="SELFTEST-PHONE")
    server_pc = start_http(state_pc, 37721)
    server_phone = start_http(state_phone, 37731)
    if server_pc is None or server_phone is None:
        print("FAIL: 端口起不来")
        return 1

    passed = 0
    failed: list[str] = []

    def check(name: str, ok: bool) -> None:
        nonlocal passed
        print(("  ok   " if ok else "  FAIL ") + name)
        if ok:
            passed += 1
        else:
            failed.append(name)

    print(f"自检目录：{base}")
    client = PeerClient("127.0.0.1", state_phone.port)
    client.device_name = "SELFTEST-PC"
    client.device_id = state_pc.host_id

    try:
        # 1. 接口
        info = client.info()
        check("info: 返回对端根目录", info.get("root") == str(phone_root))
        check("scan: 手机端能看到 note.md",
              any(it[0] == "note.md" for it in client.scan()["items"]))

        # 2. 双向
        runner = SyncRunner(client, pc_root, str(phone_root), MODE_TWO, False, False)
        stats = runner.run()
        check("双向: 电脑文件到手机", (phone_root / "sub" / "nested.docx").exists())
        check("双向: 深层目录跟着建好", (phone_root / "deep" / "x" / "y.bin").exists())
        check("双向: 二进制内容一致",
              (phone_root / "deep" / "x" / "y.bin").exists()
              and _digest(phone_root / "deep" / "x" / "y.bin") == hashlib.md5(blob).hexdigest())
        check("双向: 手机文件到电脑", (pc_root / "note.md").read_bytes() == b"from phone")
        check("双向: 相同文件不重复搬", (pc_root / "shared.txt").read_bytes() == b"same both sides")
        check("双向: 没报失败", stats["fail"] == 0)

        # 3. 电脑覆盖手机（改大一点、时间更新）
        _write(pc_root / "a.txt", b"hello from pc v2 " + os.urandom(4096), time.time())
        runner = SyncRunner(client, pc_root, str(phone_root), MODE_PUSH, False, False)
        runner.run()
        check("单向推: 手机文件被覆盖",
              (phone_root / "a.txt").read_bytes() == (pc_root / "a.txt").read_bytes())

        # 4. 手机覆盖电脑
        _write(phone_root / "note.md", b"from phone v2 " + os.urandom(2048), time.time() + 5)
        runner = SyncRunner(client, pc_root, str(phone_root), MODE_PULL, False, False)
        runner.run()
        check("单向拉: 电脑文件被覆盖",
              (pc_root / "note.md").read_bytes() == (phone_root / "note.md").read_bytes())

        # 5. 镜像删除
        _write(phone_root / "extra.txt", b"only on phone", time.time())
        runner = SyncRunner(client, pc_root, str(phone_root), MODE_PUSH, True, False)
        runner.run()
        check("镜像: 手机上多余的文件被删掉", not (phone_root / "extra.txt").exists())
        check("镜像: 电脑文件都还在", (pc_root / "a.txt").exists())

        # 6. 路径穿越要被挡住
        import urllib.error
        import urllib.request

        blocked = False
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{state_phone.port}/syn/get?rel=../pc/a.txt", timeout=3)
        except urllib.error.HTTPError as exc:
            blocked = exc.code in (400, 404)
        except Exception:
            blocked = False
        check("安全: ../ 越界被拒绝", blocked)

        # 7. 发现协议
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", 37740))
        except OSError:
            pass
        probe.settimeout(2.0)
        stop = threading.Event()
        disc_state = HostState(base / "disc", host_id="disc-pc", name="DISC-PC")
        disc_state.port = state_pc.port
        threading.Thread(target=discovery_loop, args=(disc_state, stop), daemon=True).start()
        time.sleep(0.2)
        ok = False
        try:
            payload = b"SYNSIMPLIFY/DISCOVER " + json.dumps(
                {"id": "probe", "name": "探针手机", "port": 37731}).encode()
            probe.sendto(payload, ("127.0.0.1", DISCOVERY_PORT))
            data, _ = probe.recvfrom(4096)
            ok = data.startswith(b"SYNSIMPLIFY/HOST")
            parsed = json.loads(data.split(b" ", 1)[1].decode()) if ok else {}
            ok = ok and parsed.get("port") == state_pc.port
        except Exception:
            ok = False
        finally:
            stop.set()
            probe.close()
        check("发现: 手机广播后收到 HOST 回应", ok)

        # 8. 主动广播：手机一声不吭，电脑也该被找到
        beacon_rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        beacon_rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        beacon_ok = False
        bstop = threading.Event()
        try:
            beacon_rx.bind(("0.0.0.0", 37750))
            beacon_rx.settimeout(3.0)
            beacon_state = HostState(base / "beacon", host_id="beacon-pc", name="BEACON-PC")
            beacon_state.port = state_pc.port
            threading.Thread(target=beacon_loop, args=(beacon_state, bstop, 0.2, 37750),
                             daemon=True).start()
            while True:
                data, _ = beacon_rx.recvfrom(4096)
                if data.startswith(b"SYNSIMPLIFY/HOST"):
                    beacon_ok = True
                    break
        except Exception:
            beacon_ok = False
        finally:
            bstop.set()
            beacon_rx.close()
        check("发现: 电脑主动广播，手机不广播也能找到", beacon_ok)

        # 9. GET 下载能拿到字节
        target = base / "verify.md"
        client.download("note.md", target)
        check("下载: GET 到的内容和手机一致",
              target.exists() and _digest(target) == _digest(phone_root / "note.md"))

        # 10. 端口扫描能认出「手机」（本机起个假手机顶替）
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class _FakePhone(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = json.dumps({"ok": True, "id": "probe-phone", "name": "探针手机",
                                   "root": "/sdcard/SynSimplify", "port": 37761}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        fake = ThreadingHTTPServer(("127.0.0.1", 37761), _FakePhone)
        threading.Thread(target=fake.serve_forever, daemon=True).start()
        try:
            hit = lanscan._probe("127.0.0.1", 37761)
        finally:
            fake.shutdown()
        check("扫描: 端口扫到手机并读出名字", bool(hit) and hit.get("name") == "探针手机")
    finally:
        client.close()
        server_pc.shutdown()
        server_phone.shutdown()

    total = passed + len(failed)
    print(f"\n自检 {passed}/{total} 通过" + ("" if not failed else "，失败：" + ", ".join(failed)))
    return 0 if not failed else 1


# ------------------------------------------------------------------ 入口
def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} · 同网双向文件夹同步")
    parser.add_argument("--no-gui", action="store_true", help="不启动图形界面")
    parser.add_argument("--selftest", action="store_true", help="自检后退出")
    parser.add_argument("--scan", action="store_true", help="扫描当前网段找手机，打印结果后退出")
    parser.add_argument("--port", type=int, default=0, help=f"服务端口（默认 {HTTP_PORT}）")
    parser.add_argument("--dir", default="", help="同步文件夹")
    parser.add_argument("--sync", default="", help="启动后直接同步到 IP:端口")
    parser.add_argument("--mode", default=MODE_PUSH, choices=(MODE_PUSH, MODE_PULL, MODE_TWO))
    parser.add_argument("--mirror-delete", action="store_true", help="删除对端多余的文件")
    parser.add_argument("--hidden", action="store_true", help="包含隐藏文件")
    args = parser.parse_args()

    if args.selftest:
        return run_selftest()

    if args.scan:
        return run_scan()

    cfg = load_config()
    port = args.port or int(cfg.get("port") or HTTP_PORT)
    root = Path(args.dir or cfg.get("root") or default_root())
    state = HostState(root, host_id=str(cfg.get("id") or "synsimplify"),
                      name=str(cfg.get("name") or socket.gethostname()))
    state.port = port
    state.discover_mode = "wifi" if cfg.get("discover_mode") == "wifi" else "auto"

    if args.no_gui or args.sync:
        return run_headless(state, port, args)

    try:
        from ui import HostApp
    except Exception as exc:  # noqa: BLE001
        print(f"图形界面不可用：{exc}")
        print("可以改用：python main.py --no-gui")
        return 1

    try:
        app = HostApp(state, port, cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"界面启动失败：{exc}")
        print("可以改用：python main.py --no-gui")
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
