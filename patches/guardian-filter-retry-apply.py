#!/usr/bin/python3
"""Local Hermes patch (2026-11-06): when the smart-approval guardian's provider blanks the one-word verdict with its
content filter (finish_reason=content_filter: Codex does this on some ordinary commands), ask the profile's first
`fallback_providers` entry once before escalating. An escalation in an unattended run is a refusal, so these false
positives stopped scheduled and Kanban work. Any other empty answer, error or second refusal still escalates.
Idempotent; `--check` reports. Re-run after `hermes update`, then restart the gateway."""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/tools/approval_smart.py"
MARK = "local patch (2026-11-06): guardian content-filter retry"
OLD = '''            logger.warning("Smart approvals: guardian returned an empty answer "
                           "(finish_reason=%s), escalating", finish_reason)
            return "escalate"
'''
NEW = f'''            # {MARK}: a provider's content filter is not a verdict; ask the first fallback once
            if finish_reason == "content_filter":
                try:
                    from hermes_cli.config import load_config_readonly
                    fb = (load_config_readonly().get("fallback_providers") or [None])[0] or {{}}
                    if fb.get("provider"):
                        logger.warning("Smart approvals: guardian answer blocked by a content filter; asking fallback %s",
                                       fb["provider"])
                        response = call_llm(
                            task="approval", provider=fb["provider"], model=fb.get("model"), temperature=0,
                            max_tokens=16, timeout=smart_timeout,
                            messages=[{{"role": "system", "content": system_prompt}}, {{"role": "user", "content": user_prompt}}],
                            reasoning_config=_verdict_reasoning(),
                        )
                        answer = (response.choices[0].message.content or "").strip().upper()
                        if answer:
                            return _VERDICTS.get(answer.splitlines()[-1].strip(" .*`!"), "escalate")
                except Exception as e:
                    logger.warning("Smart approvals: fallback guardian failed (%s: %s)", type(e).__name__, e)
            logger.warning("Smart approvals: guardian returned an empty answer "
                           "(finish_reason=%s), escalating", finish_reason)
            return "escalate"
'''
t = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in t else "missing")
    sys.exit(0 if MARK in t else 1)
if MARK not in t:
    assert t.count(OLD) == 1, "approval_smart.py: anchor not found once; upstream changed, patch by hand"
    t = t.replace(OLD, NEW)
    compile(t, str(F), "exec")
    bak = Path(str(F) + ".bak-2026-11-06-filterretry")
    if not bak.exists():
        shutil.copy2(F, bak)
    F.write_text(t, encoding="utf-8")
    print("patched", F)
print("ok")
