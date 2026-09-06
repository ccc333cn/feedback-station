#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Feedback Station · 真机测试反馈站 —— 局域网单文件服务(Python 3 标准库,零第三方依赖)。

    python3 server.py [--root DIR] [--port 8787] [--host 0.0.0.0] [--title 标题]

启动后打印本机内网 IP 的完整访问 URL,手机连同一 Wi-Fi 用浏览器打开即可。
--root 指向存放 checklist.json 与 data/ 的目录(默认 = 本文件所在目录);
运行数据落在 <root>/data/(results.json / bugs.json / requirements.json / uploads/),
JSON 一律「临时文件 + os.replace」原子写,写盘全程持锁。
"""

import argparse
import email
import html
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

# ── 常量 ──────────────────────────────────────────────────────────────────────

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8787
DEFAULT_TITLE = "真机反馈"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(SCRIPT_DIR, "index.html")

# 下面这组路径由 configure(root) 按 --root 现算;默认 root = 本文件所在目录。
ROOT_DIR = SCRIPT_DIR
DATA_DIR = os.path.join(ROOT_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
CHECKLIST_PATH = os.path.join(ROOT_DIR, "checklist.json")
RESULTS_PATH = os.path.join(DATA_DIR, "results.json")
BUGS_PATH = os.path.join(DATA_DIR, "bugs.json")
REQUIREMENTS_PATH = os.path.join(DATA_DIR, "requirements.json")
PAGE_TITLE = DEFAULT_TITLE

# 「新 Bug」与「新需求」两个集合结构完全一致(id/title/note/files/batchId/时间戳),
# 只差落盘文件与 id 前缀,故同一套 CRUD 走 kind 分发。
ENTRY_KINDS = {
    "bug": {"path": BUGS_PATH, "prefix": "bug", "label": "Bug"},
    "req": {"path": REQUIREMENTS_PATH, "prefix": "req", "label": "需求"},
}

# 清单还是空的时候,没带 batchId 的记录先归到这个占位批次;清单一有批次就归最新那批。
FALLBACK_BATCH_ID = "legacy"


def configure(root, title=None):
    """按 --root 重算全部数据路径(模块级常量,函数体内直接引用)。"""
    global ROOT_DIR, DATA_DIR, UPLOAD_DIR, CHECKLIST_PATH, RESULTS_PATH, BUGS_PATH
    global REQUIREMENTS_PATH, PAGE_TITLE
    ROOT_DIR = os.path.abspath(root)
    DATA_DIR = os.path.join(ROOT_DIR, "data")
    UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
    CHECKLIST_PATH = os.path.join(ROOT_DIR, "checklist.json")
    RESULTS_PATH = os.path.join(DATA_DIR, "results.json")
    BUGS_PATH = os.path.join(DATA_DIR, "bugs.json")
    REQUIREMENTS_PATH = os.path.join(DATA_DIR, "requirements.json")
    ENTRY_KINDS["bug"]["path"] = BUGS_PATH
    ENTRY_KINDS["req"]["path"] = REQUIREMENTS_PATH
    if title:
        PAGE_TITLE = title

MAX_JSON_BODY = 2 * 1024 * 1024          # 2 MB,纯文本够用
MAX_UPLOAD_BODY = 512 * 1024 * 1024      # 512 MB,够一段长录屏
CHUNK = 1 << 16
SCAN_WINDOW = 1 << 20

STATUS_VALUES = ("pass", "fail", "blocked")   # blocked = 未测试(暂留,之后补测)
TEXT_LIMIT = 20000
ID_LIMIT = 128

_EXT_OK = re.compile(r"^[A-Za-z0-9]{1,8}$")
_ID_SAFE = re.compile(r"[^A-Za-z0-9_-]")
_CT_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/heic": "heic",
    "image/heif": "heif",
    "image/gif": "gif",
    "image/webp": "webp",
    "video/quicktime": "mov",
    "video/mp4": "mp4",
}

_io_lock = threading.RLock()


# ── 小工具 ────────────────────────────────────────────────────────────────────

def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _stamp():
    t = time.time()
    return "%s-%03d" % (time.strftime("%Y%m%d-%H%M%S", time.localtime(t)), int(t * 1000) % 1000)


def _ensure_dirs():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as exc:
        # 坏档不覆盖:改名留证,回退空数据,免得一次手滑清空全部反馈
        backup = "%s.corrupt-%s" % (path, _stamp())
        try:
            os.replace(path, backup)
            sys.stderr.write("[警告] %s 解析失败（%s），已改名为 %s\n" % (path, exc, backup))
        except OSError:
            pass
        return default


def _write_json(path, obj):
    _ensure_dirs()
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_results():
    data = _read_json(RESULTS_PATH, {})
    return data if isinstance(data, dict) else {}


def _load_entries(kind):
    """读一个集合(bug / req);顺手给旧档补 batchId,免得没归属的记录哪个批次都看不见。"""
    data = _read_json(ENTRY_KINDS[kind]["path"], [])
    if not isinstance(data, list):
        return []
    entries = []
    fallback = None          # 只在真遇到缺归属的记录时才去读一次清单
    for entry in data:
        if not isinstance(entry, dict):
            continue
        batch_id = entry.get("batchId")
        if not isinstance(batch_id, str) or not batch_id.strip():
            if fallback is None:
                fallback = _newest_batch_id()
            entry["batchId"] = fallback
        entries.append(entry)
    return entries


def _load_checklist():
    data = _read_json(CHECKLIST_PATH, {"batches": []})
    return data if isinstance(data, dict) else {"batches": []}


def _newest_batch_id():
    """清单头一个批次 = 最新批次;新记录没带 batchId 时兜底用它(清单空则回退占位常量)。"""
    batches = _load_checklist().get("batches")
    if isinstance(batches, list):
        for batch in batches:
            if isinstance(batch, dict) and isinstance(batch.get("id"), str) and batch["id"]:
                return batch["id"]
    return FALLBACK_BATCH_ID


def _clip_text(value, limit=TEXT_LIMIT):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value[:limit]


def _safe_component(value):
    cleaned = _ID_SAFE.sub("_", value or "")[:64]
    return cleaned or "x"


def _safe_ext(filename, content_type):
    ext = os.path.splitext(filename or "")[1].lstrip(".").lower()
    if _EXT_OK.match(ext):
        return ext
    ext = _CT_EXT.get((content_type or "").lower().split(";")[0].strip(), "")
    if _EXT_OK.match(ext):
        return ext
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip() or "")
    guessed = (guessed or "").lstrip(".").lower()
    return guessed if _EXT_OK.match(guessed) else "bin"


def _upload_name(rel_path):
    """把记录里的 'uploads/xxx.png' 还原成安全的文件名;非法一律 None。"""
    if not isinstance(rel_path, str) or not rel_path:
        return None
    name = rel_path[len("uploads/"):] if rel_path.startswith("uploads/") else rel_path
    if not name or "/" in name or "\\" in name or name.startswith(".") or name in (".", ".."):
        return None
    return name


def _delete_upload(rel_path):
    name = _upload_name(rel_path)
    if not name:
        return False
    full = os.path.join(UPLOAD_DIR, name)
    if not _inside_uploads(full):
        return False
    try:
        os.unlink(full)
        return True
    except OSError:
        return False


def _inside_uploads(full_path):
    root = os.path.realpath(UPLOAD_DIR)
    real = os.path.realpath(full_path)
    return real == root or real.startswith(root + os.sep)


def _find_in_file(fh, needle, start):
    """在已打开的二进制文件里从 start 起向前找 needle,返回绝对偏移,找不到返回 -1。"""
    overlap = max(len(needle) - 1, 0)
    fh.seek(start)
    base = start
    buf = b""
    while True:
        chunk = fh.read(SCAN_WINDOW)
        if not chunk:
            return -1
        data = buf + chunk
        idx = data.find(needle)
        if idx != -1:
            return base + idx
        if overlap and len(data) > overlap:
            drop = len(data) - overlap
            base += drop
            buf = data[drop:]
        else:
            buf = data


def _copy_range(src, dst_path, start, end):
    remaining = max(end - start, 0)
    src.seek(start)
    with open(dst_path, "wb") as out:
        while remaining > 0:
            chunk = src.read(min(CHUNK, remaining))
            if not chunk:
                break
            out.write(chunk)
            remaining -= len(chunk)
        out.flush()
        os.fsync(out.fileno())


def lan_ip():
    """本机内网 IP:先 socket 连 8.8.8.8 的惯用法,再退回 ipconfig getifaddr en0。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(0.6)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        sock.close()
    for cmd in (["ipconfig", "getifaddr", "en0"], ["hostname", "-I"]):   # macOS / Linux
        try:
            out = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3,
            ).stdout.decode("utf-8", "ignore").split()
            if out and not out[0].startswith("127."):
                return out[0]
        except (OSError, subprocess.SubprocessError):
            pass
    return None


# ── 数据层(全部持锁 + 原子写)──────────────────────────────────────────────

def _blank_result():
    return {"status": None, "note": "", "files": [], "updatedAt": _now_iso()}


def upsert_result(item_id, status, note, has_note):
    with _io_lock:
        results = _load_results()
        record = results.get(item_id)
        if not isinstance(record, dict):
            record = _blank_result()
        record["status"] = status
        if has_note:
            record["note"] = note
        record.setdefault("note", "")
        files = record.get("files")
        record["files"] = files if isinstance(files, list) else []
        record["updatedAt"] = _now_iso()
        if status is None and not record["note"] and not record["files"]:
            results.pop(item_id, None)   # 清除:三样都空就不留残条
            _write_json(RESULTS_PATH, results)
            return {"status": None, "note": "", "files": [], "updatedAt": record["updatedAt"]}
        results[item_id] = record
        _write_json(RESULTS_PATH, results)
        return record


def append_result_file(item_id, rel_path):
    with _io_lock:
        results = _load_results()
        record = results.get(item_id)
        if not isinstance(record, dict):
            record = _blank_result()
        files = record.get("files")
        record["files"] = files if isinstance(files, list) else []
        record["files"].append(rel_path)
        record.setdefault("note", "")
        record.setdefault("status", None)
        record["updatedAt"] = _now_iso()
        results[item_id] = record
        _write_json(RESULTS_PATH, results)
        return record


def remove_result_file(item_id, rel_path):
    with _io_lock:
        results = _load_results()
        record = results.get(item_id)
        if not isinstance(record, dict):
            return None
        files = [p for p in record.get("files", []) if p != rel_path]
        record["files"] = files
        record["updatedAt"] = _now_iso()
        if record.get("status") is None and not record.get("note") and not files:
            results.pop(item_id, None)
        else:
            results[item_id] = record
        _write_json(RESULTS_PATH, results)
        _delete_upload(rel_path)
        return record


def _find_entry(entries, entry_id):
    for index, entry in enumerate(entries):
        if isinstance(entry, dict) and entry.get("id") == entry_id:
            return index
    return -1


def upsert_entry(kind, entry_id, title, note, batch_id, has_title, has_note):
    with _io_lock:
        entries = _load_entries(kind)
        if entry_id:
            index = _find_entry(entries, entry_id)
            if index < 0:
                return None
            entry = entries[index]
            if has_title:
                entry["title"] = title
            if has_note:
                entry["note"] = note
            if batch_id:
                entry["batchId"] = batch_id     # 只在显式带值时改归属,免得旧页面把它冲掉
            files = entry.get("files")
            entry["files"] = files if isinstance(files, list) else []
            entry["updatedAt"] = _now_iso()
            entries[index] = entry
        else:
            entry = {
                "id": "%s-%s-%s" % (ENTRY_KINDS[kind]["prefix"], _stamp(), uuid.uuid4().hex[:4]),
                "title": title,
                "note": note,
                "files": [],
                "batchId": batch_id or _newest_batch_id(),
                "createdAt": _now_iso(),
                "updatedAt": _now_iso(),
            }
            entries.append(entry)
        _write_json(ENTRY_KINDS[kind]["path"], entries)
        return entry


def delete_entry(kind, entry_id):
    with _io_lock:
        entries = _load_entries(kind)
        index = _find_entry(entries, entry_id)
        if index < 0:
            return None
        entry = entries.pop(index)
        _write_json(ENTRY_KINDS[kind]["path"], entries)
        for rel_path in entry.get("files", []):
            _delete_upload(rel_path)
        return entry


def append_entry_file(kind, entry_id, rel_path):
    with _io_lock:
        entries = _load_entries(kind)
        index = _find_entry(entries, entry_id)
        if index < 0:
            return None
        entry = entries[index]
        files = entry.get("files")
        entry["files"] = files if isinstance(files, list) else []
        entry["files"].append(rel_path)
        entry["updatedAt"] = _now_iso()
        _write_json(ENTRY_KINDS[kind]["path"], entries)
        return entry


def remove_entry_file(kind, entry_id, rel_path):
    with _io_lock:
        entries = _load_entries(kind)
        index = _find_entry(entries, entry_id)
        if index < 0:
            return None
        entry = entries[index]
        entry["files"] = [p for p in entry.get("files", []) if p != rel_path]
        entry["updatedAt"] = _now_iso()
        _write_json(ENTRY_KINDS[kind]["path"], entries)
        _delete_upload(rel_path)
        return entry


def entry_exists(kind, entry_id):
    with _io_lock:
        return _find_entry(_load_entries(kind), entry_id) >= 0


# ── HTTP ──────────────────────────────────────────────────────────────────────

class FeedbackHandler(BaseHTTPRequestHandler):
    server_version = "FeedbackStation/1.0"
    protocol_version = "HTTP/1.1"
    timeout = 120

    # -- 回包 --------------------------------------------------------------

    def _send_bytes(self, status, ctype, body, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body,
                         {"Cache-Control": "no-store"})

    def _fail(self, status, message, drop=False):
        if drop:
            # 请求体没读干净,keep-alive 会串包,直接断
            self.close_connection = True
        self._send_json(status, {"error": message})

    # -- 请求体 ------------------------------------------------------------

    def _content_length(self, limit):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return -1
        if length < 0 or length > limit:
            return -1
        return length

    def _read_json_body(self):
        length = self._content_length(MAX_JSON_BODY)
        if length < 0:
            return None
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _spool_body(self, limit):
        """把请求体流式落到 uploads 目录下的临时文件(同分区,后面好 os.replace)。"""
        length = self._content_length(limit)
        if length <= 0:
            return None
        _ensure_dirs()
        fd, tmp = tempfile.mkstemp(prefix=".incoming-", dir=UPLOAD_DIR)
        remaining = length
        try:
            with os.fdopen(fd, "wb") as out:
                while remaining > 0:
                    chunk = self.rfile.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        if remaining:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return None
        return tmp

    def _boundary(self):
        if self.headers.get_content_type() != "multipart/form-data":
            return None
        boundary = self.headers.get_param("boundary")
        if isinstance(boundary, tuple):
            boundary = boundary[2]
        if not boundary:
            return None
        return boundary.encode("utf-8", "ignore")

    @staticmethod
    def _first_file_part(spool_path, boundary):
        """取第一个带 filename 的部件,返回 (filename, content_type, start, end)。"""
        delim = b"--" + boundary
        size = os.path.getsize(spool_path)
        with open(spool_path, "rb") as fh:
            cursor = 0
            while cursor < size:
                mark = _find_in_file(fh, delim, cursor)
                if mark < 0:
                    return None
                after = mark + len(delim)
                fh.seek(after)
                if fh.read(2) == b"--":
                    return None                      # 结束边界
                head_end = _find_in_file(fh, b"\r\n\r\n", after)
                if head_end < 0:
                    return None
                fh.seek(after)
                raw_headers = fh.read(head_end - after).lstrip(b"\r\n")
                part = email.message_from_bytes(raw_headers)
                body_start = head_end + 4
                body_end = _find_in_file(fh, b"\r\n" + delim, body_start)
                if body_end < 0:
                    body_end = size
                filename = part.get_filename()
                if filename:
                    return (filename, part.get_content_type(), body_start, body_end)
                cursor = body_end
        return None

    # -- GET ---------------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            return self._serve_index()
        if path == "/api/state":
            return self._api_state()
        if path == "/favicon.ico":
            return self._send_bytes(204, "image/x-icon", b"")
        if path.startswith("/uploads/"):
            return self._serve_upload(path)
        return self._fail(404, "没有这个路径")

    do_HEAD = do_GET

    def _serve_index(self):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as fh:
                page = fh.read()
        except OSError:
            return self._fail(500, "index.html 读不到")
        # 每请求现读盘 + 现填占位符:改 index.html 不用重启服务
        page = page.replace("{{TITLE}}", html.escape(PAGE_TITLE))
        page = page.replace("{{DATA_DIR}}", html.escape(DATA_DIR))
        body = page.encode("utf-8")
        self._send_bytes(200, "text/html; charset=utf-8", body, {"Cache-Control": "no-store"})

    def _api_state(self):
        with _io_lock:
            payload = {
                "checklist": _load_checklist(),
                "results": _load_results(),
                "bugs": _load_entries("bug"),
                "requirements": _load_entries("req"),
            }
        self._send_json(200, payload)

    def _serve_upload(self, path):
        name = unquote(path[len("/uploads/"):])
        safe = _upload_name(name)
        if not safe:
            return self._fail(404, "没有这个文件")
        full = os.path.join(UPLOAD_DIR, safe)
        if not _inside_uploads(full) or not os.path.isfile(full):
            return self._fail(404, "没有这个文件")
        size = os.path.getsize(full)
        ctype = mimetypes.guess_type(safe)[0] or "application/octet-stream"

        start, end = 0, size - 1
        partial = False
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes=") and size:
            spec = rng[len("bytes="):].split(",")[0].strip()
            try:
                left, _, right = spec.partition("-")
                if left == "":
                    start = max(size - int(right), 0)
                else:
                    start = int(left)
                    end = int(right) if right else size - 1
                end = min(end, size - 1)
                partial = 0 <= start <= end
            except ValueError:
                partial = False
            if not partial:
                start, end = 0, size - 1

        length = end - start + 1
        headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
        }
        if partial:
            headers["Content-Range"] = "bytes %d-%d/%d" % (start, end, size)
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(full, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(CHUNK, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    # -- POST --------------------------------------------------------------

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/result":
            return self._api_result()
        if path == "/api/bug":
            return self._api_entry("bug")
        if path == "/api/bug/delete":
            return self._api_entry_delete("bug")
        if path == "/api/requirement":
            return self._api_entry("req")
        if path == "/api/requirement/delete":
            return self._api_entry_delete("req")
        if path == "/api/upload":
            return self._api_upload(parse_qs(parsed.query))
        if path == "/api/upload/delete":
            return self._api_upload_delete()
        return self._fail(404, "没有这个路径", drop=True)

    def _api_result(self):
        payload = self._read_json_body()
        if payload is None:
            return self._fail(400, "请求体不是合法 JSON", drop=True)
        item_id = _clip_text(payload.get("itemId"), ID_LIMIT).strip()
        if not item_id:
            return self._fail(400, "缺少 itemId")
        status = payload.get("status")
        if status is not None and status not in STATUS_VALUES:
            return self._fail(400, "status 只能是 pass / fail / null")
        has_note = "note" in payload
        record = upsert_result(item_id, status, _clip_text(payload.get("note")), has_note)
        self._send_json(200, {"itemId": item_id, "record": record})

    def _api_entry(self, kind):
        payload = self._read_json_body()
        if payload is None:
            return self._fail(400, "请求体不是合法 JSON", drop=True)
        entry_id = _clip_text(payload.get("id"), ID_LIMIT).strip()
        entry = upsert_entry(
            kind,
            entry_id,
            _clip_text(payload.get("title")),
            _clip_text(payload.get("note")),
            _clip_text(payload.get("batchId"), ID_LIMIT).strip(),
            "title" in payload,
            "note" in payload,
        )
        if entry is None:
            return self._fail(404, "这条%s不存在" % ENTRY_KINDS[kind]["label"])
        body = {"entry": entry}
        if kind == "bug":
            body["bug"] = entry            # 兼容旧页面(还没刷新的手机)读 data.bug
        self._send_json(200, body)

    def _api_entry_delete(self, kind):
        payload = self._read_json_body()
        if payload is None:
            return self._fail(400, "请求体不是合法 JSON", drop=True)
        entry_id = _clip_text(payload.get("id"), ID_LIMIT).strip()
        if not entry_id:
            return self._fail(400, "缺少 id")
        entry = delete_entry(kind, entry_id)
        if entry is None:
            return self._fail(404, "这条%s不存在" % ENTRY_KINDS[kind]["label"])
        self._send_json(200, {"deleted": entry_id})

    def _api_upload(self, query):
        kind = (query.get("kind") or [""])[0]
        target_id = _clip_text((query.get("id") or [""])[0], ID_LIMIT).strip()
        if kind not in ("item", "bug", "req") or not target_id:
            return self._fail(400, "kind 只能是 item / bug / req，且必须带 id", drop=True)
        if kind in ENTRY_KINDS and not entry_exists(kind, target_id):
            return self._fail(404, "这条%s不存在" % ENTRY_KINDS[kind]["label"], drop=True)
        boundary = self._boundary()
        if not boundary:
            return self._fail(400, "只收 multipart/form-data", drop=True)

        spool = self._spool_body(MAX_UPLOAD_BODY)
        if not spool:
            return self._fail(413, "请求体为空或超过上限", drop=True)
        try:
            part = self._first_file_part(spool, boundary)
            if not part:
                return self._fail(400, "没找到文件部件")
            filename, part_ctype, start, end = part
            if end - start <= 0:
                return self._fail(400, "文件是空的")
            ext = _safe_ext(filename, part_ctype)
            rel_name = "%s-%s-%s.%s" % (kind, _safe_component(target_id), _stamp(), ext)
            dest = os.path.join(UPLOAD_DIR, rel_name)
            with open(spool, "rb") as fh:
                _copy_range(fh, dest, start, end)
        finally:
            try:
                os.unlink(spool)
            except OSError:
                pass

        rel_path = "uploads/" + rel_name
        if kind == "item":
            record = append_result_file(target_id, rel_path)
        else:
            record = append_entry_file(kind, target_id, rel_path)
            if record is None:
                _delete_upload(rel_path)
                return self._fail(404, "这条%s不存在" % ENTRY_KINDS[kind]["label"])
        self._send_json(200, {"path": rel_path, "files": record.get("files", [])})

    def _api_upload_delete(self):
        payload = self._read_json_body()
        if payload is None:
            return self._fail(400, "请求体不是合法 JSON", drop=True)
        kind = _clip_text(payload.get("kind"), 16).strip()
        target_id = _clip_text(payload.get("id"), ID_LIMIT).strip()
        rel_path = _clip_text(payload.get("path"), 512).strip()
        if kind not in ("item", "bug", "req") or not target_id:
            return self._fail(400, "kind 只能是 item / bug / req，且必须带 id")
        if not _upload_name(rel_path):
            return self._fail(400, "path 不合法")
        record = remove_result_file(target_id, rel_path) if kind == "item" \
            else remove_entry_file(kind, target_id, rel_path)
        if record is None:
            return self._fail(404, "记录不存在")
        self._send_json(200, {"path": rel_path, "files": record.get("files", [])})

    # -- 杂项 --------------------------------------------------------------

    def handle_one_request(self):
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except (ConnectionResetError, BrokenPipeError, socket.timeout):
            self.close_connection = True

    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s %s\n" % (time.strftime("%H:%M:%S"), self.address_string(), fmt % args))
        sys.stdout.flush()

    def log_error(self, fmt, *args):
        text = fmt % args
        if text.startswith("Request timed out"):
            return          # keep-alive 空闲到点自然断开,不是错,别吓着看终端的人
        self.log_message("%s", text)


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Feedback Station · 局域网真机测试反馈站(零依赖)。",
    )
    parser.add_argument("--root", default=SCRIPT_DIR,
                        help="存放 checklist.json 与 data/ 的目录(默认:本脚本所在目录)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="监听端口(默认 %d)" % DEFAULT_PORT)
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="监听地址(默认 %s,局域网可达;只想本机用就填 127.0.0.1)" % DEFAULT_HOST)
    parser.add_argument("--title", default=DEFAULT_TITLE,
                        help="页面标题,建议「<项目名> · 真机反馈」(默认「%s」)" % DEFAULT_TITLE)
    return parser.parse_args(argv)


def _bootstrap_files():
    """首次启动把三份数据文件与空清单落盘,免得页面拉 state 时 404。"""
    _ensure_dirs()
    if not os.path.exists(RESULTS_PATH):
        _write_json(RESULTS_PATH, {})
    if not os.path.exists(BUGS_PATH):
        _write_json(BUGS_PATH, [])
    if not os.path.exists(REQUIREMENTS_PATH):
        _write_json(REQUIREMENTS_PATH, [])
    if not os.path.exists(CHECKLIST_PATH):
        _write_json(CHECKLIST_PATH, {"batches": []})
        print("  [提示] %s 不存在，已建一份空清单；格式参考仓库里的 checklist.example.json。"
              % CHECKLIST_PATH)


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure(args.root, args.title)
    _bootstrap_files()

    httpd = ThreadingHTTPServer((args.host, args.port), FeedbackHandler)
    httpd.daemon_threads = True
    ip = lan_ip()
    print("")
    print("  %s · 反馈站已启动" % PAGE_TITLE)
    if ip:
        print("  手机（同一 Wi-Fi）打开：  http://%s:%d/" % (ip, args.port))
    else:
        print("  没取到内网 IP，先用本机打开：  http://127.0.0.1:%d/" % args.port)
        print("  手机访问请查「系统设置 → 网络 → Wi-Fi → 详细信息」里的 IP 地址。")
    print("  本机自测：              http://127.0.0.1:%d/" % args.port)
    print("  清单文件：              %s" % CHECKLIST_PATH)
    print("  数据目录：              %s" % DATA_DIR)
    print("  Ctrl+C 停止。")
    print("")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
