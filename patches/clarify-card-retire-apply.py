#!/usr/bin/python3
"""Local Hermes patch (2026-11-10): Discord clarify cards never showed a typed answer. When a typed
message answers a pending clarify (a numeric pick, free text, or text after "Other"), or the clarify
times out or is cancelled, the gateway calls the adapter's retire_clarify_card(clarify_id, notice) so
the card stops looking answerable. Only Slack and Feishu had it; on Discord the card kept its buttons
and nothing showed that the message was taken as the answer. This adds it to the Discord adapter:
send_clarify remembers the card, and retire_clarify_card stops its buttons view, removes the buttons
and stamps the notice (for example "answered: <text>") in the card footer.
Idempotent. Flags: --check only reports, --test runs the self-test. Run it with Hermes's own python
(never with sh). Re-run after a Hermes update if --check says missing, then restart the gateway when idle."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "plugins/platforms/discord/adapter.py"
TAG = ".bak-2026-11-10-clarifyretire"
MARK = "local patch (2026-11-10): discord clarify card retire"

A1 = ('            if view:\n'
      '                send_kwargs["view"] = view\n'
      '            return send_kwargs, view\n'
      '        return await self._send_prompt(chat_id, metadata, _build, fail_log="send_clarify"')
# The rest of that call line (")" or extra local arguments such as ", team_notification=True)") is kept.
B1 = ('            if view:\n'
      '                send_kwargs["view"] = view\n'
      '            _card["view"] = view\n'
      '            return send_kwargs, view\n'
      f'        _card = {{}}  # {MARK}\n'
      '        result = await self._send_prompt(chat_id, metadata, _build, fail_log="send_clarify"')
B1_TAIL = ('        if result.success and result.message_id:\n'
      '            self._clarify_cards()[clarify_id] = (_prompt_target_id(chat_id, metadata), result.message_id, _card.get("view"))\n'
      '        return result\n'
      '\n'
      '    def _clarify_cards(self) -> dict:\n'
      f'        """{MARK}: clarify_id -> (channel id, message id, view), newest 50 kept\n'
      '        (cards answered by a click are never retired, so the map is capped instead)."""\n'
      '        cards = self.__dict__.setdefault("_hm_clarify_cards", {})\n'
      '        while len(cards) > 50:\n'
      '            cards.pop(next(iter(cards)))\n'
      '        return cards\n'
      '\n'
      '    async def retire_clarify_card(self, clarify_id: str, notice: str) -> None:\n'
      f'        """{MARK}: the clarify ended without a click (typed answer, timeout, cancel):\n'
      '        stop the buttons view, drop the buttons and stamp ``notice`` in the card footer.\n'
      '        The pop runs before the first await, so a second call for the same id is a no-op."""\n'
      '        card = self._clarify_cards().pop(clarify_id, None)\n'
      '        if card is None or not self._client:\n'
      '            return\n'
      '        target, message_id, view = card\n'
      '        if view is not None:\n'
      '            view.resolved = True  # a late click gets "already answered"\n'
      '            view.stop()  # or its own timeout stamps "expired" over the answer\n'
      '        try:\n'
      '            channel = await self._resolve_channel(target)\n'
      '            msg = await channel.fetch_message(int(message_id))\n'
      '            embed = msg.embeds[0] if msg.embeds else None\n'
      '            if embed:\n'
      '                embed.color = discord.Color.green() if notice.startswith("✅") else discord.Color.greyple()\n'
      '                embed.set_footer(text=_truncate_discord_component_text(notice, 2048))\n'
      '            await msg.edit(embed=embed, view=None)\n'
      '        except Exception:\n'
      '            logger.debug("[Discord] Could not retire clarify card %s", clarify_id, exc_info=True)\n')


def selftest():
    import asyncio
    sys.path.insert(0, str(ROOT))
    from types import SimpleNamespace as N
    from plugins.platforms.discord import adapter as A
    cls = A.DiscordAdapter
    edits, stopped = [], []

    class Embed:
        color = None
        footer = None

        def set_footer(self, text):
            self.footer = text

    emb = Embed()

    class Msg:
        embeds = [emb]

        async def edit(self, **kw):
            edits.append(kw)

    class Ch:
        async def fetch_message(self, mid):
            assert mid == 42
            return Msg()

    async def resolve(cid):
        assert cid == "555"
        return Ch()

    fake = N(_client=object(), _resolve_channel=resolve)
    fake._clarify_cards = lambda: cls._clarify_cards(fake)
    view = N(resolved=False, stop=lambda: stopped.append(1))
    fake._clarify_cards()["c1"] = ("555", "42", view)
    asyncio.run(cls.retire_clarify_card(fake, "c1", "✅ answered: option two"))
    assert view.resolved and stopped == [1], "view not stopped"
    assert edits == [{"embed": emb, "view": None}] and emb.footer == "✅ answered: option two", edits
    asyncio.run(cls.retire_clarify_card(fake, "c1", "again"))      # already retired: no-op
    asyncio.run(cls.retire_clarify_card(fake, "unknown", "x"))     # never sent here: no-op
    assert len(edits) == 1
    for i in range(60):
        fake._clarify_cards()[f"k{i}"] = ("1", "1", None)
    assert len(fake._clarify_cards()) == 50 and "k0" not in fake._clarify_cards()
    print("selftest ok 5 cases")


s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in s else "missing")
    sys.exit(0 if MARK in s else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in s:
    assert s.count(A1) == 1, "send_clarify anchor not found once; upstream changed, patch by hand"
    assert "def retire_clarify_card" not in s, "upstream Discord adapter has retire_clarify_card now; retire this patch"
    i = s.index(A1)
    j = s.index("\n", i + len(A1)) + 1
    s = s[:i] + B1 + s[i + len(A1):j] + B1_TAIL + s[j:]
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
