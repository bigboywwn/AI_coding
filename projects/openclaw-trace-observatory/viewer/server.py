#!/usr/bin/env python3
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG_PATH = os.path.expanduser("~/.openclaw/logs/lmstudio-openclaw-trace.jsonl")
DEFAULT_OPENCLAW_LOG_PATH = os.path.join("/tmp/openclaw", f"openclaw-{__import__('datetime').date.today().isoformat()}.log")


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                rows.append(
                    {
                        "kind": "parse_error",
                        "raw": line,
                        "error": str(exc),
                    }
                )
    return rows


def clear_file(path):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8"):
        pass


def read_openclaw_events(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = obj.get("1")
            payload = obj.get("1") if isinstance(obj.get("1"), dict) else None
            text = obj.get("2") if isinstance(obj.get("2"), str) else (message if isinstance(message, str) else "")
            meta = obj.get("_meta") or {}
            record = {
                "time": obj.get("time"),
                "subsystem": None,
                "text": text,
                "event": payload.get("event") if isinstance(payload, dict) else None,
                "runId": payload.get("runId") if isinstance(payload, dict) else None,
                "sessionId": payload.get("sessionId") if isinstance(payload, dict) else None,
                "sessionKey": payload.get("sessionKey") if isinstance(payload, dict) else None,
                "payload": payload,
                "raw": obj,
            }
            zero = obj.get("0")
            if isinstance(zero, str):
                try:
                    record["subsystem"] = json.loads(zero).get("subsystem")
                except Exception:
                    record["subsystem"] = zero
            if not record["runId"] and isinstance(text, str):
                import re
                match = re.search(r"runId=([a-f0-9-]+)", text)
                if match:
                    record["runId"] = match.group(1)
                match = re.search(r"sessionId=([a-f0-9-]+)", text)
                if match:
                    record["sessionId"] = match.group(1)
                match = re.search(r"lane=(session:[^ ]+)", text)
                if match:
                    record["sessionKey"] = match.group(1)
            if record["runId"] or record["sessionId"] or record["sessionKey"] or record["event"] or "agent" in (text or ""):
                rows.append(record)
    return rows


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenClawTraceViewer/1.0"

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except FileNotFoundError:
            self.send_error(404)
            return
        content_type = "text/html; charset=utf-8"
        if path.endswith(".js"):
            content_type = "application/javascript; charset=utf-8"
        elif path.endswith(".css"):
            content_type = "text/css; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/logs":
            query = urllib.parse.parse_qs(parsed.query)
            log_path = os.path.expanduser(query.get("path", [DEFAULT_LOG_PATH])[0])
            if not os.path.isfile(log_path):
                self._send_json(
                    {
                        "ok": False,
                        "error": "log_not_found",
                        "path": log_path,
                    },
                    status=404,
                )
                return
            self._send_json(
                {
                    "ok": True,
                    "path": log_path,
                    "rows": read_jsonl(log_path),
                }
            )
            return

        if parsed.path == "/api/openclaw-events":
            query = urllib.parse.parse_qs(parsed.query)
            log_path = os.path.expanduser(query.get("path", [DEFAULT_OPENCLAW_LOG_PATH])[0])
            if not os.path.isfile(log_path):
                self._send_json(
                    {
                        "ok": False,
                        "error": "log_not_found",
                        "path": log_path,
                    },
                    status=404,
                )
                return
            self._send_json(
                {
                    "ok": True,
                    "path": log_path,
                    "rows": read_openclaw_events(log_path),
                }
            )
            return

        if parsed.path in {"/", "/index.html"}:
            self._send_file(os.path.join(BASE_DIR, "index.html"))
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/logs/clear":
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception:
                payload = {}
            log_path = os.path.expanduser(payload.get("path") or DEFAULT_LOG_PATH)
            clear_file(log_path)
            self._send_json(
                {
                    "ok": True,
                    "path": log_path,
                    "cleared": True,
                }
            )
            return

        self.send_error(404)


def main():
    host = os.environ.get("TRACE_VIEWER_HOST", "127.0.0.1")
    port = int(os.environ.get("TRACE_VIEWER_PORT", "8765"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(
        f"OpenClaw trace viewer running at http://{host}:{port} "
        f"(default log: {DEFAULT_LOG_PATH})",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
