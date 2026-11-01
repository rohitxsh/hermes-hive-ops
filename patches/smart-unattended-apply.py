"""Local Hermes patch (2026-10-26, owner: "run everything in smart mode"): approvals.cron_mode / unattended_mode /
single_query_mode accept "smart". In those unattended runs the smart guardian judges a flagged command or execute_code
script: APPROVE runs it, anything else is refused (nobody can answer an escalation). Hardline floors and deny rules still
apply first; other flagged tool/file actions stay denied in smart unattended runs. Run from ~/.hermes/hermes-agent."""
import pathlib
import sys

MARK = "local patch (vm-a 2026-10-26): smart unattended approvals"
NL = chr(10)


def sub(path, old, new):
    p = pathlib.Path(path)
    s = p.read_text()
    if new in s:
        return False
    assert s.count(old) == 1, (path, old[:80], s.count(old))
    p.write_text(s.replace(old, new))
    return True


changed = []
changed.append(sub("tools/approval_context.py",
    '        return "approve" if mode in {"approve", "off", "allow", "yes"} else "deny"',
    f'        if mode == "smart":  # {MARK}: guardian decides, escalations are refused' + NL +
    '            return "smart"' + NL +
    '        return "approve" if mode in {"approve", "off", "allow", "yes"} else "deny"'))
changed.append(sub("tools/approval.py",
    '''    """Deny-mode handling for one unattended context (cron / -q / webhook); None = allow."""
    if ctx.mode() != "deny":
        return None''',
    f'''    """Deny-mode handling for one unattended context (cron / -q / webhook); None = allow."""
    mode = ctx.mode()
    if mode == "smart":  # {MARK}
        is_dangerous, pattern_key, description = detect_dangerous_command(command)
        if not is_dangerous or _is_permanently_approved(pattern_key):
            return None
        from tools.approval_smart import _smart_verdict
        if _smart_verdict(command, description, pattern_key, [pattern_key], get_current_session_key()) == "approve":
            return None
        return {{"approved": False, "message": ctx.block_message(
            f"Command flagged as dangerous ({{description}}) and the smart guardian did not approve it for an unattended run",
            noun="dangerous commands", advice="Find an alternative approach that avoids this command, or report it.")}}
    if mode != "deny":
        return None'''))
changed.append(sub("tools/approval.py",
    '''    for ctx in _unattended_contexts():
        if ctx.mode() == "deny":
            return _denied(''',
    f'''    for ctx in _unattended_contexts():
        if ctx.mode() == "smart":  # {MARK}: the guardian judges the whole script
            from tools.approval_smart import _smart_verdict
            if _smart_verdict(f"execute_code <<'PY'{{chr(10)}}{{code}}{{chr(10)}}PY", description, pattern_key, [pattern_key],
                              get_current_session_key()) == "approve":
                return _approved()
            return _denied(
                "BLOCKED by smart approval: this execute_code script was not approved for an unattended run. "
                + ctx.exec_tail, pattern_key=pattern_key, description=description, outcome="blocked", noun="code",
            )
        if ctx.mode() == "deny":
            return _denied('''))
changed.append(sub("tools/approval.py",
    '''        for ctx in _unattended_contexts():
            if ctx.mode() == "deny":
                message = deny_messages[ctx.name]''',
    f'''        for ctx in _unattended_contexts():
            if ctx.mode() in ("deny", "smart"):  # {MARK}: flagged tool/file actions stay denied
                message = deny_messages[ctx.name]'''))
# Claude as guardian sometimes explains before the verdict ("Read-only, routine.\n\nAPPROVE"); an exact-match parse
# turned that into "escalate", which unattended runs refuse. Read the verdict from the last line instead.
changed.append(sub("tools/approval_smart.py",
    '        return _VERDICTS.get(answer, "escalate")',
    f'        # {MARK}: the verdict is the last line (Claude sometimes explains first)' + NL +
    '        return _VERDICTS.get(answer.splitlines()[-1].strip(" .*`!"), "escalate")'))
print("patched" if any(changed) else "already patched", changed)
