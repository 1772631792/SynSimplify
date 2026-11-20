# -*- coding: utf-8 -*-
"""同步核心：扫描、比对、传输。

同一份逻辑在手机端（Dart）里有一份等价实现，协议写在 README 里。
这里只依赖标准库：http.client 走 HTTP/1.1 长连接，单文件流式传输。
"""

from __future__ import annotations

import errno
import http.client
import json
import os
import shutil
import threading
import time
import urllib.parse
from pathlib import Path

from config import (
    MAX_SCAN,
    MODE_PULL,
    MODE_PUSH,
    MODE_TWO,
    now_ms,
)

# 系统垃圾文件：两边都自动忽略，避免同步出无穷无尽的临时文件
JUNK_NAMES = {
    ".DS_Store", "Thumbs.db", "desktop.ini", "ehthumbs.db",
    "$RECYCLE.BIN", "System Volume Information", ".syn_part",
}
JUNK_SUFFIX = (".syn_part", ".crdownload", ".partial", ".tmp~")
CHUNK = 262144


# ----------------------------------------------------------------- 路径安全
def safe_rel(rel: str) -> str:
    """把客户端给的相对路径规整成 posix 形式，越界一律拒绝。"""
    text = (rel or "").replace("\\", "/").strip()
    text = text.strip("/")
    if not text:
        return ""
    parts = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("路径越界")
        if "\x00" in part:
            raise ValueError("非法字符")
        parts.append(part)
    return "/".join(parts)


def abs_path(root: Path, rel: str) -> Path:
    rel = safe_rel(rel)
    target = root / rel if rel else root
    try:
        resolved_root = root.resolve()
        resolved = target.resolve()
    except OSError:
        resolved_root = root
        resolved = target
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("路径越界")
    return target


# ----------------------------------------------------------------- 扫描
def scan_tree(root: Path, include_hidden: bool = False, limit: int = MAX_SCAN) -> dict:
    """深度优先列出整棵树：[[相对路径, 字节, 毫秒时间戳, 是否文件夹], ...]。"""
    root = Path(root)
    items: list[list] = []
    truncated = False
    if not root.exists():
        return {"items": items, "truncated": False, "missing": True}

    stack: list[tuple[Path, str]] = [(root, "")]
    while stack:
        folder, prefix = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            if name in JUNK_NAMES or name.endswith(JUNK_SUFFIX):
                continue
            if not include_hidden and name.startswith("."):
                continue
            rel = f"{prefix}{name}"
            try:
                if entry.is_symlink():
                    continue
                st = entry.stat(follow_symlinks=False)
                if entry.is_dir(follow_symlinks=False):
                    items.append([rel, 0, int(st.st_mtime * 1000), 1])
                    stack.append((Path(entry.path), rel + "/"))
                else:
                    items.append([rel, int(st.st_size), int(st.st_mtime * 1000), 0])
            except OSError:
                continue
            if len(items) >= limit:
                truncated = True
                return {"items": items, "truncated": truncated, "missing": False}
    items.sort(key=lambda it: it[0])
    return {"items": items, "truncated": truncated, "missing": False}


def index_of(items) -> dict:
    return {it[0]: it for it in items}


# ----------------------------------------------------------------- 计划
def make_plan(local_items, remote_items, mode: str, mirror_delete: bool = False,
              prefer: str = "pc") -> list[dict]:
    """产出操作列表。op ∈ push / pull / mkdir_remote / mkdir_local / del_remote / del_local。"""
    L = index_of(local_items)
    R = index_of(remote_items)
    ops: list[dict] = []

    l_dirs = {p for p, it in L.items() if it[3]}
    r_dirs = {p for p, it in R.items() if it[3]}

    if mode in (MODE_PUSH, MODE_TWO):
        for p in sorted(l_dirs - r_dirs, key=lambda s: s.count("/")):
            ops.append({"op": "mkdir_remote", "p": p, "s": 0, "t": 0, "why": "目录"})
    if mode in (MODE_PULL, MODE_TWO):
        for p in sorted(r_dirs - l_dirs, key=lambda s: s.count("/")):
            ops.append({"op": "mkdir_local", "p": p, "s": 0, "t": 0, "why": "目录"})

    def file_ops(push_side: str):
        src, dst = (L, R) if push_side == "push" else (R, L)
        for p, it in src.items():
            if it[3]:
                continue
            other = dst.get(p)
            if other is None:
                ops.append({"op": push_side, "p": p, "s": it[1], "t": it[2], "why": "新增"})
                continue
            if other[3]:
                ops.append({"op": "skip", "p": p, "s": it[1], "t": it[2], "why": "类型冲突"})
                continue
            if other[1] == it[1]:
                ops.append({"op": "same", "p": p, "s": it[1], "t": it[2], "why": "相同"})
                continue
            if mode == MODE_TWO:
                dt = it[2] - other[2]
                if abs(dt) <= 1500:
                    ops.append({
                        "op": push_side, "p": p, "s": it[1], "t": it[2],
                        "why": "冲突 · 以%s为准" % ("电脑" if push_side == "push" else "手机"),
                    })
                elif dt > 0:
                    ops.append({"op": "push", "p": p, "s": it[1], "t": it[2], "why": "较新"})
                else:
                    ops.append({"op": "pull", "p": p, "s": other[1], "t": other[2], "why": "较新"})
            else:
                ops.append({"op": push_side, "p": p, "s": it[1], "t": it[2], "why": "更新"})

    if mode == MODE_PUSH:
        file_ops("push")
    elif mode == MODE_PULL:
        file_ops("pull")
    else:
        # 双向：只出现一边的补齐，两边都有的按时间取新
        for p, it in L.items():
            if it[3]:
                continue
            other = R.get(p)
            if other is None:
                ops.append({"op": "push", "p": p, "s": it[1], "t": it[2], "why": "新增"})
            elif other[3]:
                ops.append({"op": "skip", "p": p, "s": it[1], "t": it[2], "why": "类型冲突"})
            elif other[1] == it[1]:
                ops.append({"op": "same", "p": p, "s": it[1], "t": it[2], "why": "相同"})
            else:
                dt = it[2] - other[2]
                if abs(dt) <= 1500:
                    ops.append({
                        "op": "push", "p": p, "s": it[1], "t": it[2],
                        "why": "冲突 · 以电脑为准",
                    })
                elif dt > 0:
                    ops.append({"op": "push", "p": p, "s": it[1], "t": it[2], "why": "电脑较新"})
                else:
                    ops.append({"op": "pull", "p": p, "s": other[1], "t": other[2], "why": "手机较新"})
        for p, it in R.items():
            if it[3] or p in L:
                continue
            ops.append({"op": "pull", "p": p, "s": it[1], "t": it[2], "why": "新增"})

    if mirror_delete and mode != MODE_TWO:
        if mode == MODE_PUSH:
            for p, it in R.items():
                if it[3]:
                    continue
                if p not in L:
                    ops.append({"op": "del_remote", "p": p, "s": it[1], "t": it[2], "why": "多余"})
        else:
            for p, it in L.items():
                if it[3]:
                    continue
                if p not in R:
                    ops.append({"op": "del_local", "p": p, "s": it[1], "t": it[2], "why": "多余"})

    order = {"mkdir_remote": 0, "mkdir_local": 0, "push": 1, "pull": 1,
             "del_remote": 2, "del_local": 2, "skip": 3, "same": 3}
    ops.sort(key=lambda o: (order.get(o["op"], 1), o["p"]))
    return ops


# ----------------------------------------------------------------- 对端客户端
class PeerClient:
    """访问对端 /syn/* 接口，长连接、断线自动重连一次。"""

    def __init__(self, ip: str, port: int, timeout: float = 12.0):
        self.ip = ip
        self.port = int(port)
        self.timeout = timeout
        self._conn: http.client.HTTPConnection | None = None
        self.device_name = ""
        self.device_id = ""

    # -- 内部
    def _connection(self) -> http.client.HTTPConnection:
        if self._conn is None:
            self._conn = http.client.HTTPConnection(self.ip, self.port, timeout=self.timeout)
        return self._conn

    def _drop(self) -> None:
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None

    def _headers(self) -> dict:
        return {
            "X-Device": urllib.parse.quote(self.device_name or "电脑"),
            "X-Device-Id": self.device_id,
        }

    def close(self) -> None:
        self._drop()

    # -- 基础
    def _request(self, method: str, path: str, body: bytes | None = None,
                 headers: dict | None = None) -> tuple[int, bytes]:
        last: Exception | None = None
        for attempt in range(2):
            conn = self._connection()
            try:
                conn.request(method, path, body=body, headers={**self._headers(), **(headers or {})})
                resp = conn.getresponse()
                data = resp.read()
                if resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status}: {data[:160].decode('utf-8', 'replace')}")
                return resp.status, data
            except (http.client.HTTPException, OSError, RuntimeError) as exc:
                last = exc
                self._drop()
                if attempt == 0:
                    time.sleep(0.15)
                    continue
                raise
        raise last or RuntimeError("请求失败")

    def get_json(self, path: str) -> dict:
        _, data = self._request("GET", path)
        try:
            return json.loads(data.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"对端返回的不是 JSON：{exc}") from exc

    def info(self) -> dict:
        return self.get_json("/syn/info")

    def scan(self, include_hidden: bool = False) -> dict:
        q = "/syn/scan" + ("?hidden=1" if include_hidden else "")
        data = self.get_json(q)
        return {
            "items": [[str(a), int(b), int(c), int(d)] for a, b, c, d in data.get("items", [])],
            "truncated": bool(data.get("truncated")),
        }

    def mkdir(self, rel: str) -> None:
        self._request("POST", "/syn/mkdir?rel=" + urllib.parse.quote(rel))

    def delete(self, rel: str) -> None:
        self._request("POST", "/syn/del?rel=" + urllib.parse.quote(rel))

    # -- 传文件
    def download(self, rel: str, dest: Path, on_progress=None) -> tuple[int, int]:
        last: Exception | None = None
        tmp = dest.with_name(dest.name + ".syn_part")
        for attempt in range(2):
            conn = self._connection()
            try:
                conn.request("GET", "/syn/get?rel=" + urllib.parse.quote(rel), headers=self._headers())
                resp = conn.getresponse()
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                total = int(resp.getheader("Content-Length") or 0)
                mtime = int(resp.getheader("X-Mtime") or 0)
                sent = 0
                t0 = time.perf_counter()
                with open(tmp, "wb") as fp:
                    while True:
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        fp.write(chunk)
                        sent += len(chunk)
                        if on_progress:
                            on_progress(sent, total, time.perf_counter() - t0)
                os.replace(tmp, dest)
                if mtime:
                    stamp = mtime / 1000.0
                    os.utime(dest, (stamp, stamp))
                return sent, mtime
            except (http.client.HTTPException, OSError, RuntimeError) as exc:
                last = exc
                self._drop()
                try:
                    tmp.unlink(missing_ok=True)  # noqa: F821
                except Exception:
                    pass
                if attempt == 0:
                    time.sleep(0.2)
                    continue
                raise
        raise last or RuntimeError("下载失败")

    def upload(self, rel: str, src: Path, mtime_ms: int, on_progress=None) -> int:
        size = src.stat().st_size
        path = (f"/syn/put?rel={urllib.parse.quote(rel)}&mtime={int(mtime_ms)}")
        last: Exception | None = None
        for attempt in range(2):
            conn = self._connection()
            try:
                conn.putrequest("POST", path, skip_accept_encoding=True)
                for key, value in self._headers().items():
                    conn.putheader(key, value)
                conn.putheader("Content-Type", "application/octet-stream")
                conn.putheader("Content-Length", str(size))
                conn.endheaders()
                sent = 0
                t0 = time.perf_counter()
                with open(src, "rb") as fp:
                    while True:
                        chunk = fp.read(CHUNK)
                        if not chunk:
                            break
                        conn.send(chunk)
                        sent += len(chunk)
                        if on_progress:
                            on_progress(sent, size, time.perf_counter() - t0)
                resp = conn.getresponse()
                body = resp.read()
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}: {body[:120].decode('utf-8', 'replace')}")
                return size
            except (http.client.HTTPException, OSError, RuntimeError) as exc:
                last = exc
                self._drop()
                if attempt == 0:
                    time.sleep(0.2)
                    continue
                raise
        raise last or RuntimeError("上传失败")


# ----------------------------------------------------------------- 执行
def _rm_rf(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


class SyncRunner:
    """一次同步任务。on_event(kind, payload) 会被同步线程直接调用。"""

    def __init__(self, client: PeerClient, local_root: Path, remote_root: str,
                 mode: str, mirror_delete: bool, include_hidden: bool,
                 on_event=None, cancel: threading.Event | None = None,
                 dry_run: bool = False, max_entries: int = MAX_SCAN):
        self.client = client
        self.local_root = Path(local_root)
        self.remote_root = remote_root
        self.mode = mode
        self.mirror_delete = mirror_delete
        self.include_hidden = include_hidden
        self.on_event = on_event or (lambda kind, payload: None)
        self.cancel = cancel or threading.Event()
        self.dry_run = dry_run
        self.max_entries = max_entries
        self.stats = {
            "up_files": 0, "up_bytes": 0,
            "down_files": 0, "down_bytes": 0,
            "skip": 0, "same": 0, "fail": 0,
            "total": 0, "elapsed": 0.0, "speed": 0.0,
        }

    def _emit(self, kind: str, payload: dict) -> None:
        try:
            self.on_event(kind, payload)
        except Exception:
            pass

    def run(self) -> dict:
        started = time.perf_counter()
        self._emit("phase", {"text": "读取手机文件列表…"})
        info = self.client.info()
        self._emit("peer", {"root": info.get("root", ""), "name": info.get("name", "")})

        local_scan = scan_tree(self.local_root, self.include_hidden, self.max_entries)
        if local_scan.get("missing"):
            self.local_root.mkdir(parents=True, exist_ok=True)
            local_scan = {"items": [], "truncated": False}
        self._emit("phase", {"text": "扫描本机文件夹…"})
        remote_scan = self.client.scan(self.include_hidden)
        if remote_scan.get("truncated") or local_scan.get("truncated"):
            self._emit("warn", {"text": f"文件太多，本次只同步前 {self.max_entries} 条"})

        plan = make_plan(local_scan["items"], remote_scan["items"], self.mode,
                         self.mirror_delete and self.mode != MODE_TWO)
        todo = [op for op in plan if op["op"] not in ("same",)]
        self.stats["total"] = len([op for op in plan if op["op"] in ("push", "pull")])
        self.stats["same"] = len([op for op in plan if op["op"] == "same"])
        self._emit("plan", {"ops": plan, "stats": dict(self.stats)})
        self._emit("phase", {"text": f"共 {len(todo)} 项操作"})

        if self.dry_run:
            self.stats["elapsed"] = time.perf_counter() - started
            self._emit("finish", {"stats": dict(self.stats), "dry": True})
            return self.stats

        failures_in_row = 0
        for op in plan:
            if self.cancel.is_set():
                self._emit("phase", {"text": "已停止"})
                break
            kind = op["op"]
            if kind in ("same", "skip"):
                if kind == "skip":
                    self.stats["skip"] += 1
                    self._emit("op_done", {"op": kind, "p": op["p"], "why": op.get("why", "")})
                continue

            self._emit("op_start", op)
            t0 = time.perf_counter()
            try:
                if kind == "mkdir_remote":
                    self.client.mkdir(op["p"])
                elif kind == "mkdir_local":
                    (abs_path(self.local_root, op["p"])).mkdir(parents=True, exist_ok=True)
                elif kind == "push":
                    src = abs_path(self.local_root, op["p"])
                    self.client.upload(
                        op["p"], src, op["t"],
                        on_progress=lambda done, total, _t, rel=op["p"]:
                            self._emit("op_progress", {"op": "push", "p": rel, "done": done, "total": total}),
                    )
                    self.stats["up_files"] += 1
                    self.stats["up_bytes"] += op.get("s", 0)
                elif kind == "pull":
                    dest = abs_path(self.local_root, op["p"])
                    self.client.download(
                        op["p"], dest,
                        on_progress=lambda done, total, _t, rel=op["p"]:
                            self._emit("op_progress", {"op": "pull", "p": rel, "done": done, "total": total}),
                    )
                    self.stats["down_files"] += 1
                    self.stats["down_bytes"] += op.get("s", 0)
                elif kind == "del_remote":
                    self.client.delete(op["p"])
                elif kind == "del_local":
                    _rm_rf(abs_path(self.local_root, op["p"]))
                failures_in_row = 0
                self._emit("op_done", {
                    "op": kind, "p": op["p"], "why": op.get("why", ""),
                    "ms": (time.perf_counter() - t0) * 1000.0, "bytes": op.get("s", 0),
                })
            except Exception as exc:  # noqa: BLE001
                self.stats["fail"] += 1
                failures_in_row += 1
                self._emit("op_fail", {"op": kind, "p": op["p"], "error": f"{type(exc).__name__}: {exc}"})
                if failures_in_row >= 4 and isinstance(exc, (OSError, http.client.HTTPException)):
                    self._emit("phase", {"text": "网络中断，同步提前结束"})
                    break
                if failures_in_row >= 12:
                    break

        self.stats["elapsed"] = time.perf_counter() - started
        moved = self.stats["up_bytes"] + self.stats["down_bytes"]
        self.stats["speed"] = (moved / 1024 / 1024) / self.stats["elapsed"] if self.stats["elapsed"] else 0
        self._emit("finish", {"stats": dict(self.stats), "dry": False})
        return self.stats


# ----------------------------------------------------------------- 本机服务辅助
def write_stream(fp, stream, length: int) -> int:
    remaining = length
    written = 0
    while remaining > 0:
        chunk = stream.read(min(CHUNK, remaining))
        if not chunk:
            break
        fp.write(chunk)
        written += len(chunk)
        remaining -= len(chunk)
    return written


def remove_quietly(path: Path) -> None:
    try:
        _rm_rf(path)
    except OSError as exc:
        if exc.errno not in (errno.ENOENT, errno.EACCES):
            raise


__all__ = [
    "PeerClient", "SyncRunner", "scan_tree", "make_plan", "safe_rel", "abs_path",
    "write_stream", "remove_quietly", "now_ms",
]
