#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional


def now_ms():
    return int(time.time() * 1000)


def ensure_parent(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def append_jsonl(path: str, record: dict) -> None:
    ensure_parent(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def safe_stderr(message: str) -> None:
    try:
        sys.stderr.write(message.rstrip("\n") + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def estimate_tokens_text(text: str) -> int:
    if not text:
        return 0
    cjk_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin_words = len(re.findall(r"[A-Za-z0-9_]+", text))
    punctuation = len(re.findall(r"[^\w\s]", text, flags=re.UNICODE))
    other_chars = max(0, len(text) - cjk_chars - sum(len(m.group(0)) for m in re.finditer(r"[A-Za-z0-9_]+", text)) - len(re.findall(r"\s", text)))
    estimate = cjk_chars + int(latin_words * 1.3) + int(punctuation * 0.3) + int(other_chars * 0.5)
    return max(1, estimate)


def flatten_content(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "text":
                    parts.append(str(item.get("text") or ""))
                elif "text" in item:
                    parts.append(str(item.get("text") or ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if "text" in value:
            return str(value.get("text") or "")
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def estimate_tokens_payload(payload: Optional[dict]) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    total = 0
    messages = payload.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                total += estimate_tokens_text(str(msg))
                continue
            total += 4
            total += estimate_tokens_text(str(msg.get("role") or ""))
            total += estimate_tokens_text(flatten_content(msg.get("content")))
            if msg.get("name"):
                total += estimate_tokens_text(str(msg.get("name")))
            if msg.get("tool_calls"):
                total += estimate_tokens_text(json.dumps(msg.get("tool_calls"), ensure_ascii=False))
        total += 2
        return total
    prompt = payload.get("prompt")
    if prompt is not None:
        return estimate_tokens_text(flatten_content(prompt))
    input_value = payload.get("input")
    if input_value is not None:
        return estimate_tokens_text(flatten_content(input_value))
    return None


def extract_text_from_response(response_json: Optional[dict], body_text: str) -> str:
    if isinstance(response_json, dict):
        choices = response_json.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message")
            if isinstance(message, dict):
                parts = [
                    flatten_content(message.get("reasoning_content")),
                    flatten_content(message.get("content")),
                ]
                combined = "\n".join(part for part in parts if part).strip()
                if combined:
                    return combined
            text_value = first.get("text")
            if text_value:
                return flatten_content(text_value)
        output = response_json.get("output")
        if isinstance(output, list):
            parts = []
            for item in output:
                if isinstance(item, dict):
                    parts.append(flatten_content(item.get("content") or item.get("text") or item))
            combined = "\n".join(part for part in parts if part).strip()
            if combined:
                return combined
    if "data:" in body_text:
        lines = []
        for raw_line in body_text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                chunk = json.loads(payload)
            except Exception:
                continue
            choices = chunk.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
            if isinstance(delta, dict):
                for key in ("reasoning_content", "content"):
                    value = flatten_content(delta.get(key))
                    if value:
                        lines.append(value)
        if lines:
            return "\n".join(lines)
    return body_text


class ProxyHandler(BaseHTTPRequestHandler):
    upstream = ""
    log_path = ""
    diag_log_path = ""
    timeout = 300
    stderr_verbose = False
    max_body_chars = 12000

    server_version = "OpenClawLMStudioTraceProxy/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def _diag(self, event: str, **fields) -> None:
        record = {
            "ts": now_ms(),
            "kind": "proxy_diag",
            "event": event,
            **fields,
        }
        line = json.dumps(record, ensure_ascii=False)
        if self.stderr_verbose:
            safe_stderr(line)
        if not self.diag_log_path:
            return
        try:
            append_jsonl(self.diag_log_path, record)
        except Exception as e:
            safe_stderr(
                json.dumps(
                    {
                        "ts": now_ms(),
                        "kind": "proxy_diag_write_error",
                        "event": event,
                        "diag_log_path": self.diag_log_path,
                        "error": repr(e),
                    },
                    ensure_ascii=False,
                )
            )

    def _safe_append_log(self, record: dict, stage: str, request_id: str) -> bool:
        try:
            append_jsonl(self.log_path, record)
            self._diag(
                "log_append_ok",
                request_id=request_id,
                stage=stage,
                log_path=self.log_path,
                record_kind=record.get("kind"),
            )
            return True
        except Exception as e:
            self._diag(
                "log_append_failed",
                request_id=request_id,
                stage=stage,
                log_path=self.log_path,
                record_kind=record.get("kind"),
                error=repr(e),
                traceback=traceback.format_exc(),
            )
            return False

    def _truncate_text(self, value: str) -> str:
        if len(value) <= self.max_body_chars:
            return value
        return value[: self.max_body_chars] + f"\n... <truncated {len(value) - self.max_body_chars} chars>"

    def _proxy(self) -> None:
        req_id = str(uuid.uuid4())
        started = now_ms()
        try:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
        except Exception:
            content_length = 0
        body = self.rfile.read(content_length) if content_length > 0 else b""
        upstream_url = self.upstream.rstrip("/") + self.path

        request_headers = {k: v for k, v in self.headers.items()}
        request_headers.pop("Host", None)
        request_headers["Connection"] = "close"
        self._diag(
            "request_received",
            request_id=req_id,
            method=self.command,
            path=self.path,
            upstream_url=upstream_url,
            content_length=content_length,
            client=self.client_address[0],
            log_path=self.log_path,
            diag_log_path=self.diag_log_path,
        )

        request_json = None
        request_json_error = None
        if body:
            try:
                request_json = json.loads(body.decode("utf-8"))
            except Exception as e:
                request_json = None
                request_json_error = repr(e)
        estimated_prompt_tokens = estimate_tokens_payload(request_json)

        request_record = {
            "ts": started,
            "kind": "openclaw_request",
            "request_id": req_id,
            "method": self.command,
            "path": self.path,
            "client": self.client_address[0],
            "headers": request_headers,
            "body_text": self._truncate_text(body.decode("utf-8", errors="replace")) if body else "",
            "body_json": request_json,
            "body_parse_error": request_json_error,
            "proxy_mode": "passthrough",
            "token_source": "estimated",
            "estimated_prompt_tokens": estimated_prompt_tokens,
        }
        self._safe_append_log(request_record, stage="request", request_id=req_id)

        req = urllib.request.Request(
            upstream_url,
            data=body if self.command in {"POST", "PUT", "PATCH"} else None,
            headers=request_headers,
            method=self.command,
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                status = resp.getcode()
                resp_headers = dict(resp.headers.items())
        except urllib.error.HTTPError as e:
            raw = e.read()
            status = e.code
            resp_headers = dict(e.headers.items())
            self._diag(
                "upstream_http_error",
                request_id=req_id,
                status=status,
                duration_ms=now_ms() - started,
                response_content_type=resp_headers.get("Content-Type"),
            )
        except Exception as e:
            error_record = {
                "ts": now_ms(),
                "kind": "proxy_error",
                "request_id": req_id,
                "method": self.command,
                "path": self.path,
                "upstream_url": upstream_url,
                "error": repr(e),
                "duration_ms": now_ms() - started,
            }
            self._safe_append_log(error_record, stage="proxy_error", request_id=req_id)
            self._diag(
                "upstream_exception",
                request_id=req_id,
                error=repr(e),
                traceback=traceback.format_exc(),
                duration_ms=now_ms() - started,
            )
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "proxy_upstream_error", "detail": repr(e)}).encode("utf-8"))
            return

        response_json = None
        usage = None
        body_text = raw.decode("utf-8", errors="replace")
        response_json_error = None
        try:
            response_json = json.loads(body_text)
            usage = response_json.get("usage") if isinstance(response_json, dict) else None
        except Exception as e:
            response_json = None
            response_json_error = repr(e)

        completion_text = extract_text_from_response(response_json, body_text)
        estimated_completion_tokens = estimate_tokens_text(completion_text) if completion_text else 0
        estimated_total_tokens = (
            (estimated_prompt_tokens or 0) + estimated_completion_tokens
            if estimated_prompt_tokens is not None
            else None
        )

        response_record = {
            "ts": now_ms(),
            "kind": "lmstudio_response",
            "request_id": req_id,
            "method": self.command,
            "path": self.path,
            "upstream_url": upstream_url,
            "status": status,
            "duration_ms": now_ms() - started,
            "headers": resp_headers,
            "body_text": self._truncate_text(body_text),
            "body_json": response_json,
            "body_parse_error": response_json_error,
            "usage": usage,
            "usage_prompt_tokens": usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            "usage_completion_tokens": usage.get("completion_tokens") if isinstance(usage, dict) else None,
            "usage_total_tokens": usage.get("total_tokens") if isinstance(usage, dict) else None,
            "proxy_mode": "passthrough",
            "token_source": "provider" if isinstance(usage, dict) else "estimated",
            "response_text": completion_text,
            "estimated_prompt_tokens": estimated_prompt_tokens,
            "estimated_completion_tokens": estimated_completion_tokens,
            "estimated_total_tokens": estimated_total_tokens,
        }
        self._safe_append_log(response_record, stage="response", request_id=req_id)
        self._diag(
            "upstream_response_ready",
            request_id=req_id,
            status=status,
            duration_ms=now_ms() - started,
            response_content_type=resp_headers.get("Content-Type"),
            raw_bytes=len(raw),
            has_usage=isinstance(usage, dict),
            body_parse_error=response_json_error,
        )

        self.send_response(status)
        for key, value in resp_headers.items():
            lower = key.lower()
            if lower in {"transfer-encoding", "connection", "content-encoding"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
            self._diag(
                "client_response_sent",
                request_id=req_id,
                status=status,
                bytes_sent=len(raw),
                duration_ms=now_ms() - started,
            )
        except Exception as e:
            self._diag(
                "client_write_failed",
                request_id=req_id,
                status=status,
                bytes_attempted=len(raw),
                error=repr(e),
                traceback=traceback.format_exc(),
            )
            raise

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace proxy between OpenClaw and LM Studio")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=12434)
    parser.add_argument("--upstream", default="http://127.0.0.1:1234")
    parser.add_argument("--log-file", default=os.path.expanduser("~/.openclaw/logs/lmstudio-openclaw-trace.jsonl"))
    parser.add_argument("--diag-log-file", default=os.path.expanduser("~/.openclaw/logs/lmstudio-openclaw-trace.diag.jsonl"))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--stderr-verbose", action="store_true")
    parser.add_argument("--max-body-chars", type=int, default=12000)
    args = parser.parse_args()

    ProxyHandler.upstream = args.upstream.rstrip("/")
    ProxyHandler.log_path = os.path.expanduser(args.log_file)
    ProxyHandler.diag_log_path = os.path.expanduser(args.diag_log_file)
    ProxyHandler.timeout = args.timeout
    ProxyHandler.stderr_verbose = args.stderr_verbose
    ProxyHandler.max_body_chars = max(1000, args.max_body_chars)

    ensure_parent(ProxyHandler.log_path)
    ensure_parent(ProxyHandler.diag_log_path)
    startup_record = {
        "ts": now_ms(),
        "kind": "proxy_startup",
        "listen_host": args.listen_host,
        "listen_port": args.listen_port,
        "upstream": ProxyHandler.upstream,
        "log_path": ProxyHandler.log_path,
        "diag_log_path": ProxyHandler.diag_log_path,
        "log_dir_writable": os.access(os.path.dirname(os.path.abspath(ProxyHandler.log_path)), os.W_OK),
        "diag_dir_writable": os.access(os.path.dirname(os.path.abspath(ProxyHandler.diag_log_path)), os.W_OK),
        "pid": os.getpid(),
        "python": sys.version,
        "cwd": os.getcwd(),
    }
    try:
        append_jsonl(ProxyHandler.diag_log_path, startup_record)
    except Exception as e:
        safe_stderr(json.dumps({"kind": "proxy_startup_diag_write_failed", "error": repr(e)}, ensure_ascii=False))
    try:
        append_jsonl(ProxyHandler.log_path, startup_record)
    except Exception as e:
        safe_stderr(
            json.dumps(
                {
                    "kind": "proxy_startup_log_write_failed",
                    "log_path": ProxyHandler.log_path,
                    "error": repr(e),
                },
                ensure_ascii=False,
            )
        )
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), ProxyHandler)
    print(
        f"OpenClaw LM Studio trace proxy listening on http://{args.listen_host}:{args.listen_port} "
        f"-> {ProxyHandler.upstream} | log={ProxyHandler.log_path} | diag={ProxyHandler.diag_log_path}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
