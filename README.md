# telecom-noc-agent

[![CI](https://github.com/nikhil2sharma/telecom-noc-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/nikhil2sharma/telecom-noc-agent/actions/workflows/ci.yml)

An AI assistant for 4G core (EPC) network operations, built with the
[Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview).

It exposes network KPIs to Claude as **in-process MCP tools**, so the model
answers health-check and root-cause questions from tool data instead of
guessing.

> **Disclaimer:** This is an independent personal project, built for learning
> and demonstration. It is not affiliated with, endorsed by, or derived from any
> employer, vendor or operator. All bundled data is **synthetic**. Network
> concepts used (MME, SGW, PGW, HSS, GTP, S1/S11/S6a) come from public 3GPP
> specifications.

## Features

- In-process MCP tools (no separate server process):
  - `list_nodes`: list monitored nodes and their type
  - `get_node_kpi`: fetch KPIs for a node, with input validation and normalization
- Pluggable data source: point `--data` at any JSON file in the same format
- Streaming responses, structured logging (stderr), meaningful exit codes
- Unit tests for tool logic that run without calling the API

## How it works

```
User question ──> Claude (Agent SDK) ──tool call──> list_nodes / get_node_kpi
                         ^                                   │
                         └──────────── KPI JSON ─────────────┘
```

1. KPIs are loaded from a JSON file into memory.
2. The tools are registered on an in-process MCP server.
3. Claude decides which tools to call, reads the results and writes the answer.

## Requirements

- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- Authentication: log in once with `claude`, or set `ANTHROPIC_API_KEY`
  (the Claude Code CLI is bundled with `claude-agent-sdk`)

## Quick start

```bash
uv sync
uv run noc_agent.py
uv run noc_agent.py "What is the attach success rate of MME-01?"
uv run noc_agent.py --model claude-sonnet-5-5 --max-turns 5 -v "Give an RCA for PGW-02"
```

## Using your own data

Create a JSON file in this format and pass it with `--data`:

```json
{
  "nodes": {
    "PGW-02": {"type": "PGW", "session_success_rate": 94.1, "gtp_echo_timeouts": 27}
  }
}
```

```bash
uv run noc_agent.py --data path/to/kpis.json "Which nodes look unhealthy?"
```

See [data/sample_kpis.json](data/sample_kpis.json) for a full example.

## Development

```bash
uv run pytest        # no API calls; tools are tested directly
uv run ruff check .
```

CI runs lint, format check, tests and a secret scan on every push.

## Exit codes

| Code | Meaning |
|------|---------|
| 0    | Success |
| 1    | Data load, SDK or agent error |
| 2    | Claude Code CLI not found |
| 130  | Interrupted (Ctrl+C) |

## Project layout

```
noc_agent.py            Agent, tools and CLI
data/sample_kpis.json   Synthetic demo data
tests/test_tools.py     Unit tests for tool logic
.github/workflows/      CI: lint, tests, secret scan
```

## License

[MIT](LICENSE)
