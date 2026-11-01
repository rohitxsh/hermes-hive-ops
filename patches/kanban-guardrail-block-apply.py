#!/usr/bin/python3
"""Local Hermes patch (2026-11-01, the owner: "apply the 4 recommended changes"): when Hermes's tool loop guard halts a
kanban worker (e.g. the same skill_view repeated 5-10 times), the worker used to end with "I stopped retrying ... Tell me
how you'd like to proceed" and no board call. The dispatcher booked that as a protocol-violation crash and respawned the
task from scratch (18 of 28 crashed runs on vm-b, 24-31 Oct). With this patch the halted worker blocks its card
(kind needs_input) with the reason, so a person sees it instead of a silent crash-and-restart loop. Only for
dispatcher-owned kanban workers that haven't already handed the card off; chats are unchanged.
Idempotent; `--check` only reports; `--test` runs the self-test with Hermes's venv python. Lives in
~/agents/src/hermes-local-patches/; re-run after `hermes update` if the self-check says it's missing."""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/agent/turn_tool_round.py"
TAG = ".bak-2026-11-01-guardblock"
MARK = "local patch (2026-11-01): kanban guardrail halt -> block"
ANCHOR = ('        agent._emit_diagnostic_status(f"⚠️ Tool guardrail halted {decision.tool_name}: {decision.code}")\n')
CALL = (f"        # {MARK}\n"
        "        _kanban_block_on_halt(messages, decision)\n")
HELPER = f'''

def _kanban_block_on_halt(messages, decision) -> None:
    """{MARK}: a halted kanban worker blocks its card with the reason instead of exiting with plain text,
    which the dispatcher books as a protocol-violation crash and respawns from scratch."""
    log = logging.getLogger(__name__)
    try:
        from agent.kanban_stop import kanban_stop_nudge_enabled, session_called_kanban_terminal
        if not kanban_stop_nudge_enabled() or session_called_kanban_terminal(messages):
            return
        from tools.kanban_tools import _handle_block
        reason = (f"Hermes's loop guard stopped this run: {{decision.tool_name or 'a tool'}} was called "
                  f"{{decision.count}} times without progress ({{decision.code}}). Retry it, or narrow the task.")
        log.info("kanban guardrail halt -> kanban_block: %s", str(_handle_block({{"reason": reason, "kind": "needs_input"}}))[:200])
    except Exception:
        log.debug("kanban guardrail halt -> block failed", exc_info=True)
'''


def selftest():
    sys.path.insert(0, str(Path.home() / ".hermes/hermes-agent"))
    from types import SimpleNamespace as N
    import agent.kanban_stop as ks
    import tools.kanban_tools as kt
    from agent import turn_tool_round as T
    calls = []
    kt._handle_block = lambda args, **kw: calls.append(args) or '{"ok": true}'
    d = N(tool_name="skill_view", count=10, code="idempotent_no_progress_block")
    ks.kanban_stop_nudge_enabled = lambda: True
    ks.session_called_kanban_terminal = lambda m: False
    T._kanban_block_on_halt([], d)
    assert len(calls) == 1 and calls[0]["kind"] == "needs_input" and "skill_view" in calls[0]["reason"], calls
    ks.session_called_kanban_terminal = lambda m: True     # already handed off: leave it
    T._kanban_block_on_halt([], d)
    ks.session_called_kanban_terminal = lambda m: False
    ks.kanban_stop_nudge_enabled = lambda: False           # not a kanban worker (chat, cron): leave it
    T._kanban_block_on_halt([], d)
    assert len(calls) == 1, calls
    src = F.read_text(encoding="utf-8")
    assert src.index(ANCHOR) < src.index("_kanban_block_on_halt(messages, decision)") < src.index('append_message(messages, {"role": "assistant", "content": final_response})')
    print("selftest ok 3 cases")


s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in s else "missing")
    sys.exit(0 if MARK in s else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in s:
    assert s.count(ANCHOR) == 1, "anchor not found once; upstream changed, patch by hand"
    assert "\nimport logging\n" in s
    s = s.replace(ANCHOR, ANCHOR + CALL).rstrip("\n") + "\n" + HELPER
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
