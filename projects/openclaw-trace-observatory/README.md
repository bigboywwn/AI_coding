# OpenClaw Trace Observatory

This project captures a local OpenClaw tracing toolkit built around:

- an LM Studio proxy that records model request/response traffic
- a browser viewer that visualizes prompt growth across rounds
- sample logs that let the viewer be replayed without rebuilding the environment

## Goal

Make it easy to inspect how one OpenClaw task is decomposed into multiple model inference requests, how prompt size changes round by round, and what changed between adjacent prompts.

## Tech Stack

- Python 3 standard library (`http.server`, JSON parsing)
- Plain HTML/CSS/JavaScript for the local viewer
- JSONL log files from:
  - LM Studio proxy trace
  - OpenClaw structured gateway logs

## Layout

```text
projects/openclaw-trace-observatory/
├── README.md
├── scripts/
│   └── lmstudio_openclaw_trace_proxy.py
├── viewer/
│   ├── index.html
│   └── server.py
└── samples/
    └── logs/
        ├── lmstudio-openclaw-trace.jsonl
        └── openclaw-2026-03-25.log
```

## How To Run

### 1. Start the LM Studio trace proxy

The proxy script sits between OpenClaw and LM Studio. It forwards requests to
LM Studio unchanged, while logging:

- raw OpenClaw request payloads
- raw LM Studio responses
- extracted response text
- fallback token estimates when provider-side `usage` is missing

Example:

```bash
cd projects/openclaw-trace-observatory/scripts
python3 lmstudio_openclaw_trace_proxy.py \
  --listen-host 127.0.0.1 \
  --listen-port 12434 \
  --upstream http://127.0.0.1:1234 \
  --log-file ~/.openclaw/logs/lmstudio-openclaw-trace.jsonl
```

Default flags:

- `--listen-host`: proxy bind host, default `127.0.0.1`
- `--listen-port`: proxy bind port, default `12434`
- `--upstream`: LM Studio base URL, default `http://127.0.0.1:1234`
- `--log-file`: JSONL output path, default `~/.openclaw/logs/lmstudio-openclaw-trace.jsonl`
- `--timeout`: upstream request timeout in seconds, default `300`

The log file will contain paired records like:

- `kind: "openclaw_request"`
- `kind: "lmstudio_response"`

Useful fields:

- `request_id`
- `estimated_prompt_tokens`
- `estimated_completion_tokens`
- `estimated_total_tokens`
- `usage_prompt_tokens` / `usage_completion_tokens` when LM Studio returns them
- `response_text`

Current behavior note:

- the proxy runs in `passthrough` mode
- when LM Studio streaming responses do not include `usage`, token counts are
  estimated locally from prompt/response text

### 2. Point OpenClaw at the proxy

Update the OpenClaw provider base URL so requests go through the proxy:

```json
{
  "models": {
    "providers": {
      "local": {
        "baseUrl": "http://127.0.0.1:12434/v1"
      }
    }
  }
}
```

LM Studio remains the real model backend. The proxy only adds observability.

### 3. Start the viewer

Start the viewer locally:

```bash
cd projects/openclaw-trace-observatory/viewer
python3 server.py
```

Open:

```text
http://127.0.0.1:8765
```

Default data sources:

- LM Studio proxy trace: `~/.openclaw/logs/lmstudio-openclaw-trace.jsonl`
- OpenClaw structured file log: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`

The UI also supports:

- reloading another log path
- clearing the current proxy log
- correlating flows with probable OpenClaw `runId` / `sessionId` events

### 4. Feed the viewer with both log sources

By default the viewer reads:

- proxy trace: `~/.openclaw/logs/lmstudio-openclaw-trace.jsonl`
- OpenClaw structured file log: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`

The second file is important because it can expose OpenClaw-side metadata such
as probable `runId`, `sessionId`, timeout events, and embedded-run failures.
The viewer uses this as a heuristic second source to correlate high-level
OpenClaw runs with low-level model requests.

## Current Status

- Proxy trace script copied from the working OpenClaw local setup
- Viewer supports prompt delta highlighting and approximate run correlation
- Sample logs included for reproducible inspection
- Current run correlation is heuristic because `runId` is not directly forwarded inside the proxied LM Studio request body
