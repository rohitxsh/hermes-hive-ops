"""outbound-guard: a pre_tool_call leak guard: when a tool call that sends data
off this machine (messages, browser typing/navigation/scripts, web searches, network commands, network code) contains what
looks like a payment card number (Luhn-valid, known prefixes), an Aadhaar number (Verhoeff-valid) or a PAN, Hermes asks
the owner for approval first (fail-closed: unattended runs are blocked). browser_vault fills are not checked: the agent
never sees those values. Bank account numbers have no reliable pattern and are not checked. Matches are logged masked
to ~/.hermes/logs/outbound-guard.log. Local files a call uploads (curl @file/-T, gh --body-file/-F, scp/rsync sources,
MEDIA:/path attachments, file paths in message arguments) are read and checked too; one that exists but can't be read, or a
text file over 20 MB, needs approval as well. Logging never decides: if the log can't be written, approval is still
required. `python3 __init__.py --selftest`."""
import hashlib
import json
import os
import re
import shlex
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


def _date_stamp(s):
    """YYYYMMDD-HHMM / YYYYMMDDHHMM file and folder stamps; Aadhaar numbers written spaced (4 4 4) are still checked."""
    if not re.fullmatch(r"20\d{6}-?\d{4}", s):
        return False
    try:
        time.strptime(s[:8] + s[-4:], "%Y%m%d%H%M")
        return True
    except ValueError:
        return False


def find(text):
    """[(kind, masked)] for sensitive-looking values in text."""
    out = []
    for m in CARD.finditer(text):
        d = re.sub(r"\D", "", m.group())
        if len(set(d)) > 1 and _card_prefix(d) and _luhn(d):
            out.append(("payment card number", f"****{d[-4:]}"))
    for m in AADHAAR.finditer(text):
        d = re.sub(r"\D", "", m.group())
        if len(d) == 12 and len(set(d)) > 1 and _verhoeff(d) and not _date_stamp(m.group()):
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


MAX_FILE = 20 << 20
_UPLOAD_FLAGS = {"-T", "--upload-file", "--body-file", "-F", "--data-binary", "--data", "-d", "--form"}


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _strings(x)


def _uploaded_paths(tool_name, args, text):
    """Local files this call would send: curl/gh file arguments, scp/rsync sources, MEDIA:/path, path-valued arguments."""
    found = [m for v in _strings(args) for m in re.findall(r"MEDIA:(\S+)", v)]
    if tool_name == "terminal":
        try:
            toks = shlex.split(text)
        except ValueError:
            toks = text.split()
        copy = bool(toks) and os.path.basename(toks[0]) in ("scp", "rsync")
        for i, t in enumerate(toks):
            if t.startswith("@"):
                found.append(t[1:])
            elif "=@" in t:
                found.append(t.split("=@", 1)[1])
            elif t.startswith("--body-file="):
                found.append(t.split("=", 1)[1])
            elif i and toks[i - 1] in _UPLOAD_FLAGS:
                found.append(t)
            elif copy and i and not t.startswith("-") and ":" not in t:
                found.append(t)
    elif tool_name != "execute_code":
        found += [v for v in _strings(args) if v.startswith(("/", "~/")) and "\n" not in v and len(v) < 4096]
    # shortcut: relative paths resolve against the call's workdir or the gateway's TERMINAL_CWD, not a cwd changed by an
    # earlier `cd`; a path that doesn't resolve is skipped. Code in execute_code that opens files isn't followed either.
    base = str(args.get("workdir") or os.environ.get("TERMINAL_CWD") or os.getcwd())
    out = []
    for f in found:
        f = os.path.join(base, os.path.expanduser(f.split(";", 1)[0]))   # curl's "file;type=..." suffix
        if os.path.isfile(f) and f not in out:
            out.append(f)
    return out


def _file_hits(path):
    """Hits in a local text file; an existing file that can't be checked counts as a hit."""
    # shortcut: binary uploads (images, APKs) aren't inspected; add per-format checks if sensitive files go out as binaries
    name = os.path.basename(path)
    try:
        with open(path, "rb") as fh:
            head = fh.read(8192)
            if b"\0" in head:
                return []
            if os.path.getsize(path) > MAX_FILE:
                return [("file too large to check", name)]
            data = head + fh.read()
    except OSError:
        return [("file that could not be read", name)]
    return [(k, f"{m} in {name}") for k, m in find(data.decode("utf-8", "ignore"))]


def _log(tool_name, what):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {os.environ.get('HERMES_PROFILE', '?')} {tool_name}: {what}\n")
    except Exception:
        pass   # the log is a record only: the approval must not depend on it


def pre_tool_call(tool_name=None, args=None, **kwargs):
    try:
        args = args if isinstance(args, dict) else {}
        text = _outbound_text(tool_name or "", args)
        hits = find(text) if text else []
        for f in (_uploaded_paths(tool_name, args, text) if text else []):
            hits += _file_hits(f)
    except Exception:
        return None  # a guard bug must not break every tool call
    if not hits:
        return None
    what = ", ".join(sorted({f"{k} ({m})" for k, m in hits}))
    _log(tool_name, what)
    key = "outbound-guard:" + hashlib.sha256((text + what).encode()).hexdigest()[:16]  # "always" covers only this exact call
    return {"action": "approve", "rule_key": key,
            "message": f"outbound-guard: this {tool_name} call would send {what} off this machine. "
                       "Approve only if you meant to share it."}


def register(ctx):
    ctx.register_hook("pre_tool_call", pre_tool_call)


if __name__ == "__main__":
    import tempfile
    _tmp = tempfile.TemporaryDirectory(prefix="outbound-guard-selftest-")
    LOG = os.path.join(_tmp.name, "masked.log")
    assert find("card 4111 1111 1111 1111 exp") == [("payment card number", "****1111")]
    assert find("pay 4111111111111112") == []                       # Luhn fails
    assert find("discord:200000000000000002 thread 200000000000000003") == []   # Discord IDs
    assert find("aadhaar 2341 2341 2346") and find("aadhaar 2341 2341 2346")[0][0] == "Aadhaar number"
    assert find("head 9f2ab234123412346cd41f and 4111111111111111e0a") == []     # hex SHAs
    assert find("cp -r qa/pr38-evidence-20261106-0006/ x && 202611060006.png") == []   # date-time stamps
    assert find("aadhaar 2026 1106 0006")[0][0] == "Aadhaar number"                    # same digits, spaced: checked
    assert find("aadhaar 2026-1106-0006") and find("id 202613060001")                  # not a stamp / no 13th month
    assert find("PAN ABCPE1234F") == [("PAN", "AB*******F")]
    assert find("ticket 1793531152 and ts 1793473582.3978465") == []
    assert pre_tool_call("send_message", {"message": "my card 4111111111111111"})["action"] == "approve"
    assert pre_tool_call("terminal", {"command": "echo 4111111111111111 > notes.txt"}) is None    # local only
    assert pre_tool_call("terminal", {"command": "curl -d pan=ABCPE1234F https://x"})["action"] == "approve"
    assert pre_tool_call("browser_vault", {"item": "4111111111111111"}) is None
    assert pre_tool_call("read_file", {"path": "ABCPE1234F"}) is None
    # a log that can't be written must not drop the approval (a file sits where the log's folder should be)
    open(LOG, "a").close()
    LOG = os.path.join(LOG, "sub", "masked.log")
    assert pre_tool_call("send_message", {"message": "my card 4111111111111111"})["action"] == "approve"
    # uploaded file contents
    csv, clean, png = (os.path.join(_tmp.name, n) for n in ("customer.csv", "notes.md", "shot.png"))
    with open(csv, "w") as fh:
        fh.write("name,card\nA,4111 1111 1111 1111\n")
    with open(clean, "w") as fh:
        fh.write("nothing sensitive\n")
    with open(png, "wb") as fh:
        fh.write(b"\x89PNG\0\0 4111111111111111")
    assert pre_tool_call("terminal", {"command": f"curl --data-binary @{csv} https://x"})["action"] == "approve"
    assert pre_tool_call("terminal", {"command": f"curl -F 'f=@{csv};type=text/csv' https://x"})["action"] == "approve"
    assert pre_tool_call("terminal", {"command": "gh pr comment 5 -F customer.csv", "workdir": _tmp.name})["action"] == "approve"
    assert pre_tool_call("terminal", {"command": f"scp {csv} host:/tmp/"})["action"] == "approve"
    assert pre_tool_call("send_message", {"message": f"report MEDIA:{csv}"})["action"] == "approve"
    assert pre_tool_call("send_message", {"message": "see", "file": csv})["action"] == "approve"
    assert pre_tool_call("terminal", {"command": f"gh pr comment 5 --body-file {clean}"}) is None
    assert pre_tool_call("terminal", {"command": f"curl -F f=@{png} https://x"}) is None             # binary: skipped
    assert pre_tool_call("terminal", {"command": f"cat {csv} > /tmp/x"}) is None                     # not sent
    assert pre_tool_call("terminal", {"command": "curl -d @missing.csv https://x"}) is None          # nothing to read
    if os.geteuid() != 0:
        os.chmod(csv, 0)
        assert "could not be read" in pre_tool_call("terminal", {"command": f"curl -d @{csv} https://x"})["message"]
    print("selftest ok")
