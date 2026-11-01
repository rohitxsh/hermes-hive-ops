"""Run web_extract_tool through Hermes's own plugin loading, as the agent would (no LLM call)."""
import asyncio
import json
import logging
import sys

sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
from hermes_cli.plugins import discover_plugins  # noqa: E402

discover_plugins()
from tools import web_tools  # noqa: E402

print("extract backend:", web_tools._get_extract_backend())
out = json.loads(asyncio.run(web_tools.web_extract_tool(sys.argv[1:], char_limit=4000)))
for r in out.get("results", out if isinstance(out, list) else []):
    print(r.get("url"), "->", len(r.get("content") or ""), "chars", "error:" if r.get("error") else "", r.get("error") or "")
