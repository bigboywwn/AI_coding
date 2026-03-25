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

## Current Status

- Proxy trace script copied from the working OpenClaw local setup
- Viewer supports prompt delta highlighting and approximate run correlation
- Sample logs included for reproducible inspection
- Current run correlation is heuristic because `runId` is not directly forwarded inside the proxied LM Studio request body
