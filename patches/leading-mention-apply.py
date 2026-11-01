#!/usr/bin/python3
"""Local Hermes patch (2026-11-01, the owner: "if a message starts with an @mention of someone else, Hermes ignores it, on
all VMs and all channels/agents"): people can talk to each other in an agent's channel or thread without the agent
answering. Hermes's own DISCORD_IGNORE_NO_MENTION doesn't cover this here, because it skips free-response channels and
bot threads, which is every agent channel on these VMs. The gate drops a server-channel message whose text starts with
a user mention that isn't the bot, a role mention that isn't one of the bot's roles, or @everyone/@here. A mention
later in the text, or a message starting with the bot's own mention, is answered as before. DMs are untouched.
Idempotent; `--check` only reports; `--test` runs the self-test with Hermes's python. Lives in
~/agents/src/hermes-local-patches/; re-run after `hermes update` if the self-check says it's missing, then restart the
gateway when idle."""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/plugins/platforms/discord/adapter.py"
TAG = ".bak-2026-11-01-leadmention"
MARK = "local patch (2026-11-01): leading mention of someone else"
PAIRS = [
    ("        raw_self_mention = self._self_is_explicitly_mentioned(message)\n",
     f"        # {MARK}: the message is for that person, not the agent\n"
     "        if not isinstance(message.channel, discord.DMChannel) and self._leads_with_other_mention(message):\n"
     "            logger.debug(\"[%s] admission: dropping message %s — starts with a mention of someone else\",\n"
     "                         self.name, getattr(message, \"id\", \"?\"))\n"
     "            return False, False\n"
     "        raw_self_mention = self._self_is_explicitly_mentioned(message)\n"),
    ("    def _self_is_explicitly_mentioned(self, message: Any) -> bool:\n",
     "    def _leads_with_other_mention(self, message: Any) -> bool:\n"
     f"        \"\"\"{MARK}: True when the text starts with @everyone/@here, a user mention that isn't the bot, or a\n"
     "        role mention that isn't one of the bot's roles.\"\"\"\n"
     "        text = (getattr(message, \"content\", \"\") or \"\").lstrip()\n"
     "        if text.startswith((\"@everyone\", \"@here\")):\n"
     "            return True\n"
     "        m = re.match(r\"<@([!&]?)(\\d+)>\", text)\n"
     "        if not m or not self._client or not self._client.user:\n"
     "            return False\n"
     "        if m.group(1) == \"&\":\n"
     "            me = getattr(getattr(message, \"guild\", None), \"me\", None)\n"
     "            return m.group(2) not in {str(r.id) for r in getattr(me, \"roles\", None) or []}\n"
     "        return m.group(2) != str(self._client.user.id)\n\n"
     "    def _self_is_explicitly_mentioned(self, message: Any) -> bool:\n"),
]


def selftest():
    sys.path.insert(0, str(Path.home() / ".hermes/hermes-agent"))
    from types import SimpleNamespace as N
    from plugins.platforms.discord import adapter as A
    fn = A.DiscordAdapter._leads_with_other_mention if hasattr(A, "DiscordAdapter") else next(
        getattr(c, "_leads_with_other_mention") for c in vars(A).values()
        if isinstance(c, type) and hasattr(c, "_leads_with_other_mention"))
    me = N(_client=N(user=N(id=111)))
    guild = N(me=N(roles=[N(id=555)]))
    cases = {
        "<@222> can you check this": True, "  <@!222> hi": True, "<@&999> team, look": True,
        "@everyone heads up": True, "@here quick one": True,
        "<@111> what's pending?": False, "<@!111> hi": False, "<@&555> do this": False,
        "hey <@222> look": False, "what's pending?": False, "": False,
    }
    for text, want in cases.items():
        got = fn(me, N(content=text, guild=guild))
        assert got == want, (text, got, want)
    src = F.read_text(encoding="utf-8")
    assert src.index(MARK + ": the message is for that person") < src.index("raw_self_mention = self._self_is_explicitly_mentioned(message)\n        if not isinstance(message.channel, discord.DMChannel) and (")
    print("selftest ok", len(cases), "cases")


s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in s else "missing")
    sys.exit(0 if MARK in s else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in s:
    for a, b in PAIRS:
        assert s.count(a) == 1, ("anchor not found once; upstream changed, patch by hand", a[:60])
        s = s.replace(a, b)
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
