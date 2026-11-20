# -*- coding: utf-8 -*-
"""本机 HTTP 服务：手机来拉文件、推文件、问列表，都走这里。

接口（和手机端 Dart 实现一一对应）：
    GET  /syn/ping                 心跳 + 测延迟
    GET  /syn/info                 电脑名 / 同步文件夹 / 版本
    GET  /syn/scan?hidden=1        整棵树 [[rel,size,mtime,isDir], ...]
    GET  /syn/get?rel=路径         下载单个文件
    POST /syn/put?rel=&mtime=      上传单个文件（请求体就是文件）
    POST /syn/mkdir?rel=           建目录
    POST /syn/del?rel=             删除
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config import APP_NAME, APP_VER, PORT_SPAN, PROTO_VER
from state import HostState
from sync import CHUNK, abs_path, remove_quietly, safe_rel, scan_tree, write_stream


def make_handler(state: HostState, port: int):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = f"SynSimplifyHost/{APP_VER}"

        # -------------------------------------------------------- 基础
        def log_message(self, fmt, *args):
            pass

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _query(self) -> dict:
            q = urllib.parse.urlparse(self.path).query
            return {k: v[0] for k, v in urllib.parse.parse_qs(q).items()}

        def _client(self) -> tuple[str, str, str]:
            ip = self.client_address[0] if self.client_address else ""
            device = urllib.parse.unquote(self.headers.get("X-Device", "") or "")
            device_id = self.headers.get("X-Device-Id", "") or ""
            return ip, device, device_id

        def _hello(self) -> None:
            ip, device, device_id = self._client()
            if device or device_id:
                state.note_peer(ip, {"name": device, "id": device_id})

        # -------------------------------------------------------- GET
        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path == "/syn/ping":
                self._hello()
                self._json(200, {"ok": True, "name": state.name, "t": int(time.time() * 1000)})
            elif path == "/syn/info":
                self._hello()
                snap = state.snapshot()
                self._json(200, {
                    "ok": True,
                    "name": snap["name"],
                    "id": snap["id"],
                    "hue": snap["hue"],
                    "port": port,
                    "root": snap["root"],
                    "rootName": Path(snap["root"]).name or snap["root"],
                    "ver": PROTO_VER,
                    "app": APP_VER,
                    "status": snap["status"],
                    "busy": snap["status"] == "running",
                })
            elif path == "/syn/scan":
                self._hello()
                q = self._query()
                hidden = q.get("hidden") in ("1", "true", "yes")
                root = state.get_root()
                result = scan_tree(root, include_hidden=hidden)
                self._json(200, {
                    "ok": True,
                    "root": str(root),
                    "items": result["items"],
                    "truncated": result["truncated"],
                })
            elif path == "/syn/get":
                self._hello()
                self._serve_file()
            elif path == "/":
                self._json(200, {"ok": True, "app": APP_NAME, "ver": APP_VER,
                                 "root": str(state.get_root())})
            else:
                self.close_connection = True
                self._json(404, {"ok": False, "error": "not found"})

        def _serve_file(self):
            q = self._query()
            try:
                root = state.get_root()
                target = abs_path(root, q.get("rel", ""))
            except ValueError as exc:
                self.close_connection = True
                self._json(400, {"ok": False, "error": str(exc)})
                return

            if not target.is_file():
                self.close_connection = True
                self._json(404, {"ok": False, "error": "file not found"})
                return

            try:
                size = target.stat().st_size
                mtime = int(target.stat().st_mtime * 1000)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(size))
                self.send_header("X-Mtime", str(mtime))
                self.send_header("X-Name", urllib.parse.quote(target.name))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(target, "rb") as fp:
                    while True:
                        chunk = fp.read(CHUNK)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.close_connection = True

        # -------------------------------------------------------- POST
        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            if path == "/syn/put":
                self._receive_file()
            elif path == "/syn/mkdir":
                self._mkdir()
            elif path == "/syn/del":
                self._delete()
            else:
                self.close_connection = True
                self._json(404, {"ok": False, "error": "not found"})

        def _mkdir(self):
            self._hello()
            q = self._query()
            try:
                target = abs_path(state.get_root(), q.get("rel", ""))
                target.mkdir(parents=True, exist_ok=True)
            except (ValueError, OSError) as exc:
                self.close_connection = True
                self._json(400, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            self._json(200, {"ok": True, "rel": safe_rel(q.get("rel", ""))})

        def _delete(self):
            self._hello()
            q = self._query()
            try:
                rel = safe_rel(q.get("rel", ""))
                if not rel:
                    raise ValueError("不能删同步根目录")
                target = abs_path(state.get_root(), rel)
                remove_quietly(target)
            except (ValueError, OSError) as exc:
                self.close_connection = True
                self._json(400, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            self._json(200, {"ok": True})

        def _receive_file(self):
            self._hello()
            q = self._query()
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                self.close_connection = True
                self._json(400, {"ok": False, "error": "empty body"})
                return

            rel_raw = q.get("rel", "")
            try:
                rel = safe_rel(rel_raw)
                if not rel:
                    raise ValueError("缺少文件名")
                root = state.get_root()
                target = abs_path(root, rel)
            except ValueError as exc:
                # 不读请求体，直接断开，避免连接被脏数据污染
                self.close_connection = True
                self._json(400, {"ok": False, "error": str(exc)})
                return

            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_dir():
                    remove_quietly(target)
                tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.syn_part")
                with open(tmp, "wb") as fp:
                    written = write_stream(fp, self.rfile, length)
                if written != length:
                    tmp.unlink(missing_ok=True)
                    self.close_connection = True
                    self._json(400, {"ok": False, "error": "上传中断"})
                    return
                os.replace(tmp, target)
                mtime = q.get("mtime")
                if mtime:
                    try:
                        stamp = int(mtime) / 1000.0
                        os.utime(target, (stamp, stamp))
                    except (ValueError, OSError):
                        pass
            except OSError as exc:
                self.close_connection = True
                self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return

            self._json(200, {"ok": True, "rel": rel, "bytes": length})

    return Handler


class SyncHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_http(state: HostState, port: int) -> ThreadingHTTPServer | None:
    for candidate in range(port, port + PORT_SPAN):
        try:
            server = SyncHTTPServer(("0.0.0.0", candidate), make_handler(state, candidate))
        except OSError:
            continue
        state.port = candidate
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server
    return None


def fake_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
