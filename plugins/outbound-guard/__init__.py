"""outbound-guard (2026-11-01, the owner: Duet-inspired leak guard). A pre_tool_call hook: when a tool call that sends data
off this VM (messages, browser typing/navigation/scripts, web searches, network commands, network code) contains what
looks like a payment card number (Luhn-valid, known prefixes), an Aadhaar number (Verhoeff-valid) or a PAN, Hermes asks
the owner for approval first (fail-closed: unattended runs are blocked). browser_vault fills are not checked: the agent
never sees those values. Bank account numbers have no reliable pattern and are not checked. Matches are logged masked
to ~/.hermes/logs/outbound-guard.log. `python3 __init__.py --selftest`."""
import hashlib
import json
import os
import re
import time

LOG = os.path.expanduser("~/.hermes/logs/outbound-guard.log")
ALWAYS = {"send_message", "browser_type", "browser_navigate", "browser_console", "browser_exec", "browser_cdp",
          "web_search", "web_extract", "x_search", "delegate_task"}
NET_CMD = re.compile(r"\b(curl|wget|http|https|himalaya|sendmail|mail|mutt|ssh|scp|rsync|nc|ncat|gh|git\s+push|ftp)\b")
NET_CODE = re.compile(r"\b(requests|urllib|httpx|aiohttp|smtplib|socket|http\.client|websocket|fetch)\b")

# letters/underscore count as neighbours too, so digit runs inside git SHAs and other hex IDs are not matched
CARD = re.compile(r"(?<![\w.])(?:\d[ -]?){14,18}\d(?![\w.])")
AADHAAR = re.compile(r"(?<![\w.])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![\w.])")
PAN = re.compile(r"\b[A-Z]{3}[PCHABGJLFT][A-Z]\d{4}[A-Z]\b")
_V_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_V_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def _luhn(d):
    s = 0
    for i, c in enumerate(reversed(d)):
        n = int(c) * (2 if i % 2 else 1)
        s += n - 9 if n > 9 else n
    return s % 10 == 0


def _verhoeff(d):
    c = 0
    for i, ch in enumerate(reversed(d)):
        c = _V_D[c][_V_P[i % 8][int(ch)]]
    return c == 0


def _card_prefix(d):
    return (len(d) == 15 and d[:2] in ("34", "37")) or (len(d) == 16 and (
        d[0] == "4" or 51 <= int(d[:2]) <= 55 or 2221 <= int(d[:4]) <= 2720 or d[:4] == "6011" or d[:2] in ("65", "60", "35", "81", "82")))


def find(text):
    """[(kind, masked)] for sensitive-looking values in text."""
    out = []
    for m in CARD.finditer(text):
        d = re.sub(r"\D", "", m.group())
        if len(set(d)) > 1 and _card_prefix(d) and _luhn(d):
            out.append(("payment card number", f"****{d[-4:]}"))
    for m in AADHAAR.finditer(text):
        d = re.sub(r"\D", "", m.group())
        if len(d) == 12 and len(set(d)) > 1 and _verhoeff(d):
            out.append(("Aadhaar number", f"********{d[-4:]}"))
    for m in PAN.finditer(text):
        out.append(("PAN", f"{m.group()[:2]}*******{m.group()[-1]}"))
    return out


def _outbound_text(tool_name, args):
    if tool_name in ALWAYS or tool_name.startswith("discord"):
        return json.dumps(args, default=str)
    if tool_name == "terminal":
        cmd = str(args.get("command", ""))
        return cmd if NET_CMD.search(cmd) else ""
    if tool_name == "execute_code":
        code = str(args.get("code", ""))
        return code if NET_CODE.search(code) else ""
    return ""


def pre_tool_call(tool_name=None, args=None, **kwargs):
    try:
        text = _outbound_text(tool_name or "", args if isinstance(args, dict) else {})
        hits = find(text) if text else []
        if not hits:
            return None
        what = ", ".join(sorted({f"{k} ({m})" for k, m in hits}))
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {os.environ.get('HERMES_PROFILE', '?')} {tool_name}: {what}\n")
        key = "outbound-guard:" + hashlib.sha256(text.encode()).hexdigest()[:16]  # "always" covers only this exact call
        return {"action": "approve", "rule_key": key,
                "message": f"outbound-guard: this {tool_name} call would send {what} off this machine. "
                           "Approve only if you meant to share it."}
    except Exception:
        return None  # a guard bug must not break every tool call


def register(ctx):
    ctx.register_hook("pre_tool_call", pre_tool_call)


if __name__ == "__main__":
    LOG = "/tmp/outbound-guard-selftest.log"
    assert find("card 4111 1111 1111 1111 exp") == [("payment card number", "****1111")]
    assert find("pay 4111111111111112") == []                       # Luhn fails
    assert find("discord:200000000000000002 thread 200000000000000003") == []   # Discord IDs
    assert find("aadhaar 2341 2341 2346") and find("aadhaar 2341 2341 2346")[0][0] == "Aadhaar number"
    assert find("head 9f2ab234123412346cd41f and 4111111111111111e0a") == []     # hex SHAs
    assert find("PAN ABCPE1234F") == [("PAN", "AB*******F")]
    assert find("ticket 1793531152 and ts 1793473582.3978465") == []
    assert pre_tool_call("send_message", {"message": "my card 4111111111111111"})["action"] == "approve"
    assert pre_tool_call("terminal", {"command": "echo 4111111111111111 > notes.txt"}) is None    # local only
    assert pre_tool_call("terminal", {"command": "curl -d pan=ABCPE1234F https://x"})["action"] == "approve"
    assert pre_tool_call("browser_vault", {"item": "4111111111111111"}) is None
    assert pre_tool_call("read_file", {"path": "ABCPE1234F"}) is None
    print("selftest ok")
