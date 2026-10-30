"""NOC assistant agent for a 4G EPC core, built on the Claude Agent SDK.

Exposes EPC node KPIs to Claude through in-process MCP tools, then asks
Claude a question and streams the answer to stdout.

All bundled data is synthetic and for demonstration only.

Usage:
    uv run noc_agent.py "Is PGW-02 healthy? Give a short RCA."
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    CLINotFoundError,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

log = logging.getLogger("noc_agent")

DEFAULT_QUESTION = "Is PGW-02 healthy? Give a short RCA."

SYSTEM_PROMPT = (
    "You are a 4G core (EPC) NOC assistant. "
    "Always use the provided tools to fetch KPI data; never guess KPI values. "
    "Use list_nodes to discover available nodes. "
    "If a node is not found, say so clearly."
)

DEFAULT_DATA_FILE = Path(__file__).parent / "data" / "sample_kpis.json"

# In-memory KPI store: node_id -> KPI dict. Populated by load_kpis().
NODE_KPI: dict[str, dict] = {}


def load_kpis(path: Path) -> dict[str, dict]:
    """Load node KPIs from a JSON file of the form {"nodes": {node_id: {...}}}."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        raise ValueError(f"{path}: expected a 'nodes' object")
    return {node_id.upper(): kpi for node_id, kpi in nodes.items()}


def _text_result(text: str, is_error: bool = False) -> dict:
    """Build an MCP tool result containing a single text block."""
    result: dict = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["is_error"] = True
    return result


@tool(
    "get_node_kpi",
    "Fetch live KPIs of an EPC node (MME/SGW/PGW) by node_id, e.g. 'PGW-02'.",
    {"node_id": str},
)
async def get_node_kpi(args: dict) -> dict:
    raw = args.get("node_id")
    if not isinstance(raw, str) or not raw.strip():
        return _text_result("node_id must be a non-empty string", is_error=True)

    node = raw.strip().upper()  # normalize, e.g. "pgw-02 " -> "PGW-02"
    log.info("Tool call: get_node_kpi(%s)", node)

    kpi = NODE_KPI.get(node)
    if kpi is None:
        known = ", ".join(sorted(NODE_KPI))
        return _text_result(f"Node {node} not found. Known nodes: {known}", is_error=True)
    return _text_result(json.dumps({"node_id": node, **kpi}))


@tool("list_nodes", "List all monitored EPC nodes with their node type.", {})
async def list_nodes(args: dict) -> dict:
    log.info("Tool call: list_nodes()")
    nodes = {node_id: kpi.get("type", "unknown") for node_id, kpi in sorted(NODE_KPI.items())}
    return _text_result(json.dumps(nodes))


TOOLS = [get_node_kpi, list_nodes]


def build_options(model: str | None, max_turns: int) -> ClaudeAgentOptions:
    noc_server = create_sdk_mcp_server(name="noc", version="1.0.0", tools=TOOLS)
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"noc": noc_server},
        allowed_tools=[f"mcp__noc__{t.name}" for t in TOOLS],
        model=model,
        max_turns=max_turns,
    )


async def run(question: str, options: ClaudeAgentOptions) -> int:
    """Send one question to Claude and print the answer. Returns an exit code."""
    exit_code = 0
    async with ClaudeSDKClient(options=options) as client:
        await client.query(question)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text, flush=True)
            elif isinstance(msg, ResultMessage):
                if msg.total_cost_usd is not None:
                    log.info("Done in %d turn(s), cost $%.4f", msg.num_turns, msg.total_cost_usd)
                if msg.is_error:
                    log.error("Agent finished with an error: %s", msg.subtype)
                    exit_code = 1
    return exit_code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="4G EPC NOC assistant powered by Claude.")
    parser.add_argument(
        "question",
        nargs="?",
        default=DEFAULT_QUESTION,
        help="Question to ask the agent (default: %(default)r)",
    )
    parser.add_argument(
        "--model", default=None, help="Claude model ID to use (default: Claude Code's default)"
    )
    parser.add_argument(
        "--max-turns", type=int, default=5, help="Maximum agent turns (default: %(default)s)"
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_FILE,
        help="Path to KPI JSON file (default: bundled synthetic data)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, which cannot print emoji/unicode.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        NODE_KPI.update(load_kpis(args.data))
    except (OSError, ValueError) as exc:
        log.error("Failed to load KPI data: %s", exc)
        return 1
    log.info("Loaded %d node(s) from %s", len(NODE_KPI), args.data)

    options = build_options(args.model, args.max_turns)
    try:
        return anyio.run(run, args.question, options)
    except CLINotFoundError:
        log.error("Claude Code CLI not found. Reinstall dependencies with: uv sync")
        return 2
    except ClaudeSDKError as exc:
        log.error("Claude SDK error: %s", exc)
        return 1
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
