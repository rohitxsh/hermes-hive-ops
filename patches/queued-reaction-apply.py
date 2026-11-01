#!/usr/bin/python3
"""Local Hermes patch (2026-11-01: queued messages did not get the same reactions): with
display.busy_input_mode: queue, a message sent while an agent is busy is stored durably and later run by
gateway/session_ingress.execute_admission, which calls the handler directly, so the adapter's processing hooks
(👀 while working, ✅/❌ when done) never fired for it. Part 1 fires them around that call for queued native chat
messages (not automation or API rows). Part 2 lets the Discord adapter react to a message rebuilt from the queue:
it has the Discord message ID but no live message object, so a partial message is built from the channel.
Idempotent; `--check` only reports; `--test` runs the self-test with Hermes's venv python. Re-run after
`hermes update` if the self-check says it's missing, then restart the gateway when idle."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F1 = ROOT / "gateway/session_ingress.py"
F2 = ROOT / "plugins/platforms/discord/adapter.py"
TAG = ".bak-2026-11-01-queuedreact"
MARK = "local patch (2026-11-01): queued-message reactions"

A1 = "            response = await authority.runner._handle_message(event)\n"
B1 = (f"            # {MARK}: the adapter's 👀/✅ hooks, as for a message handled directly\n"
      "            from gateway.platforms.base import ProcessingOutcome as _PO\n"
      "            from gateway.run_turn_followup_ack import _followup_cancel_outcome, _run_followup_processing_hook\n"
      "            _ack = _queued_ack_adapter(authority, event, row)\n"
      "            if _ack is not None:\n"
      "                await _run_followup_processing_hook(_ack, event, 'on_processing_start')\n"
      "            try:\n"
      "                response = await authority.runner._handle_message(event)\n"
      "            except asyncio.CancelledError:\n"
      "                if _ack is not None:\n"
      "                    await _run_followup_processing_hook(_ack, event, 'on_processing_complete', _followup_cancel_outcome(_ack))\n"
      "                raise\n"
      "            except BaseException:\n"
      "                if _ack is not None:\n"
      "                    await _run_followup_processing_hook(_ack, event, 'on_processing_complete', _PO.FAILURE)\n"
      "                raise\n"
      "            if _ack is not None:\n"
      "                await _run_followup_processing_hook(_ack, event, 'on_processing_complete', _PO.SUCCESS)\n")
H1 = f'''

def _queued_ack_adapter(authority, event, row):
    """{MARK}: the adapter that should acknowledge a queued native chat message, or None
    (automation, API and other non-native rows stay silent)."""
    try:
        if getattr(event, "internal", False) or "native_text_v1" not in (row.get("payload") or {{}}):
            return None
        runner = authority.runner
        finder = getattr(runner, "_intake_adapter_for", None)
        adapter = finder(event.source) if finder else None
        if adapter is None:  # restored rows fail closed there; the platform's adapter shares the bot
            adapter = (getattr(runner, "adapters", None) or {{}}).get(event.source.platform)
        return adapter
    except Exception:
        return None
'''
A2 = ("    async def on_processing_start(self, event: MessageEvent) -> None:\n"
      "        \"\"\"Add an in-progress reaction and record durable handling state.\"\"\"\n"
      "        message = event.raw_message\n")
B2 = ("    async def _reaction_target(self, event: MessageEvent) -> Any:\n"
      f"        \"\"\"{MARK}: the live message, or a partial message rebuilt from the IDs a queued\n"
      "        event keeps (it has no live discord.Message), so it can still get reactions.\"\"\"\n"
      "        message = event.raw_message\n"
      "        if message is not None and hasattr(message, \"add_reaction\"):\n"
      "            return message\n"
      "        mid = str(getattr(event, \"message_id\", \"\") or \"\")\n"
      "        src = getattr(event, \"source\", None)\n"
      "        cid = str(getattr(src, \"thread_id\", None) or getattr(src, \"chat_id\", \"\") or \"\")\n"
      "        if not (mid.isdigit() and cid.isdigit() and self._client):\n"
      "            return message\n"
      "        try:\n"
      "            channel = await self._resolve_channel(cid)\n"
      "            return channel.get_partial_message(int(mid))\n"
      "        except Exception:\n"
      "            return message\n\n"
      "    async def on_processing_start(self, event: MessageEvent) -> None:\n"
      "        \"\"\"Add an in-progress reaction and record durable handling state.\"\"\"\n"
      "        message = await self._reaction_target(event)\n")
A3 = ("        if not self._reactions_enabled():\n"
      "            return\n"
      "        message = event.raw_message\n"
      "        if hasattr(message, \"add_reaction\"):\n"
      "            await self._remove_reaction(message, \"👀\")\n")
B3 = ("        if not self._reactions_enabled():\n"
      "            return\n"
      "        message = await self._reaction_target(event)\n"
      "        if hasattr(message, \"add_reaction\"):\n"
      "            await self._remove_reaction(message, \"👀\")\n")


def selftest():
    import asyncio
    sys.path.insert(0, str(ROOT))
    from types import SimpleNamespace as N
    from gateway import session_ingress as si
    ev = N(internal=False, source=N(platform="discord"))
    disc = object()
    auth = N(runner=N(_intake_adapter_for=lambda s: None, adapters={"discord": disc}))
    assert si._queued_ack_adapter(auth, ev, {"payload": {"native_text_v1": {}}}) is disc   # falls back to the platform adapter
    assert si._queued_ack_adapter(auth, ev, {"payload": {"text": "x"}}) is None             # non-native row: silent
    assert si._queued_ack_adapter(auth, N(internal=True, source=ev.source), {"payload": {"native_text_v1": {}}}) is None
    from plugins.platforms.discord import adapter as A
    cls = next(c for c in vars(A).values() if isinstance(c, type) and hasattr(c, "_reaction_target"))
    got = {}

    class Ch:
        def get_partial_message(self, mid):
            got["mid"] = mid
            return N(add_reaction=lambda e: None, id=mid)

    async def resolve(cid):
        got["cid"] = cid
        return Ch()
    fake = N(_client=object(), _resolve_channel=resolve)
    queued = N(raw_message=None, message_id="1234567890", source=N(thread_id="555", chat_id="444"))
    msg = asyncio.run(cls._reaction_target(fake, queued))
    assert msg.id == 1234567890 and got == {"cid": "555", "mid": 1234567890}, got
    live = N(add_reaction=lambda e: None)
    assert asyncio.run(cls._reaction_target(fake, N(raw_message=live, message_id="1", source=None))) is live
    assert asyncio.run(cls._reaction_target(fake, N(raw_message=None, message_id="adm_x", source=N(thread_id=None, chat_id="444")))) is None
    print("selftest ok 6 cases")


s1, s2 = F1.read_text(encoding="utf-8"), F2.read_text(encoding="utf-8")
if "--check" in sys.argv:
    ok = MARK in s1 and MARK in s2
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in s1:
    assert s1.count(A1) == 1, "session_ingress anchor not found once; upstream changed, patch by hand"
    s1 = s1.replace(A1, B1).rstrip("\n") + "\n" + H1
    compile(s1, str(F1), "exec")
    if not Path(str(F1) + TAG).exists():
        shutil.copy2(F1, str(F1) + TAG)
    F1.write_text(s1, encoding="utf-8")
    print("patched", F1)
if MARK not in s2:
    assert s2.count(A2) == 1 and s2.count(A3) == 1, "discord adapter anchors not found once; patch by hand"
    s2 = s2.replace(A2, B2).replace(A3, B3)
    compile(s2, str(F2), "exec")
    if not Path(str(F2) + TAG).exists():
        shutil.copy2(F2, str(F2) + TAG)
    F2.write_text(s2, encoding="utf-8")
    print("patched", F2)
print("ok")
