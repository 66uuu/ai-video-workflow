#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
shotboard_server —— 分镜无限画布看板的本地服务（零第三方依赖）
================================================================
作用：让浏览器里的 tldraw 无限画布能读到本机的时间轴 JSON 和首帧图。

浏览器安全模型不允许 file:// 页面随便读任意本地路径，所以起一个本地
HTTP 服务做三件事：
  1) 把 frontend/dist 的静态页面吐给浏览器
  2) /api/scan   扫描成果区，列出所有「时间轴 / 审计」JSON
  3) /api/load   读取某个 JSON（限白名单目录）
  4) /api/image  读取某张本地图片（限白名单目录，用于首帧缩略图）

用法：
  python server.py                # 默认 http://127.0.0.1:8080
  $env:SHOTBOARD_PORT="9000"; python server.py

安全：只允许访问 ALLOWED_ROOTS 下的文件，其余一律拒绝；不做目录遍历。
"""
import json
import os
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "frontend", "dist")

PORT = int(os.environ.get("SHOTBOARD_PORT", "8080"))
HOST = "127.0.0.1"

# 允许访问的根目录（防路径穿越，其它一律 403）
ALLOWED_ROOTS = [
    os.path.abspath(r"你的桌面\AI产物"),
    os.path.abspath(r"你的桌面\AI生成视频"),
]

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ico": "image/x-icon",
    ".map": "application/json",
    ".txt": "text/plain; charset=utf-8",
}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# 扫描时跳过的目录名
SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", ".venv", "venv"}


def norm(p):
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def is_allowed(path):
    p = norm(path)
    for root in ALLOWED_ROOTS:
        r = norm(root)
        if p == r or p.startswith(r + os.sep):
            return True
    return False


def scan_files():
    """扫描白名单目录，找出时间轴 / 审计 JSON。返回按 mtime 倒序。"""
    out = []
    for root in ALLOWED_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if not fn.lower().endswith(".json"):
                    continue
                low = fn.lower()
                if ("timeline" in low) or ("_audit" in low):
                    full = os.path.join(dirpath, fn)
                    try:
                        st = os.stat(full)
                    except OSError:
                        continue
                    out.append({
                        "path": full,
                        "name": fn,
                        "dir": dirpath,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    })
    out.sort(key=lambda x: -x["mtime"])
    return out


def scan_images(base_dir):
    """在 base_dir 及其祖先目录里找「Sxx」命名的首帧图，返回 {shot_id: 绝对路径}。"""
    mapping = {}
    if not base_dir or not isinstance(base_dir, str) or not is_allowed(base_dir):
        return mapping
    roots = []
    d = os.path.abspath(base_dir)
    for _ in range(5):
        if d not in roots:
            roots.append(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in IMG_EXT:
                    continue
                m = re.search(r"(?:EP\d+_)?(S\d+[A-Za-z]?)[_\-.]", fn)
                if not m:
                    continue
                sid = m.group(1)
                if sid not in mapping:
                    mapping[sid] = os.path.join(dirpath, fn)
    return mapping


class Handler(BaseHTTPRequestHandler):
    server_version = "ShotboardServer/1.0"

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/api/roots":
            return self._json(200, {"ok": True, "roots": ALLOWED_ROOTS})

        if path == "/api/scan":
            return self._json(200, {"ok": True, "files": scan_files()})

        if path == "/api/scan-images":
            d = (qs.get("dir", [""])[0]).strip()
            return self._json(200, {"ok": True, "images": scan_images(d)})

        if path == "/api/load":
            p = (qs.get("path", [""])[0]).strip()
            if not p or not is_allowed(p) or not os.path.isfile(p):
                return self._json(400, {"ok": False, "error": "路径不存在或不在白名单内"})
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:  # noqa
                return self._json(500, {"ok": False, "error": str(e)})
            return self._json(200, {"ok": True, "path": p, "data": data})

        if path == "/api/image":
            p = (qs.get("path", [""])[0]).strip()
            ext = os.path.splitext(p)[1].lower()
            if not p or not is_allowed(p) or not os.path.isfile(p) or ext not in IMG_EXT:
                return self._json(400, {"ok": False, "error": "图片不存在 / 不在白名单内 / 类型不支持"})
            with open(p, "rb") as f:
                blob = f.read()
            return self._send(200, blob, MIME.get(ext, "application/octet-stream"),
                              extra={"Cache-Control": "no-cache"})

        return self._serve_static(path)

    def _serve_static(self, p):
        rel = urllib.parse.unquote(p.lstrip("/"))
        if rel == "":
            rel = "index.html"
        full = os.path.normpath(os.path.join(DIST, rel))
        # 防目录穿越 + SPA 回退
        if not (norm(full) == norm(DIST) or norm(full).startswith(norm(DIST) + os.sep)):
            full = os.path.join(DIST, "index.html")
        if not os.path.isfile(full):
            full = os.path.join(DIST, "index.html")
        try:
            with open(full, "rb") as f:
                blob = f.read()
        except OSError:
            return self._send(404, b"not found", "text/plain")
        ext = os.path.splitext(full)[1].lower()
        return self._send(200, blob, MIME.get(ext, "application/octet-stream"))

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def main():
    print("=" * 62)
    print("  分镜 · 无限画布看板  server")
    print("  地址: http://%s:%d" % (HOST, PORT))
    print("  白名单目录:")
    for r in ALLOWED_ROOTS:
        print("    - %s" % r)
    if not os.path.isfile(os.path.join(DIST, "index.html")):
        print("\n  [警告] 未找到 frontend/dist/index.html")
        print("         请先执行: cd frontend && npm install && npm run build")
        print("         然后重新运行本脚本。")
    print("=" * 62)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        srv.server_close()


if __name__ == "__main__":
    main()