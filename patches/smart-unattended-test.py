"""Unit check of the smart-unattended patch with the guardian mocked (no model call). Run with Hermes's venv from ~/.hermes/hermes-agent."""
import sys
sys.path.insert(0, ".")
import tools.approval as A
import tools.approval_context as C
import tools.approval_smart as S

C._binary_approval_mode.__globals__["cfg_get"] = lambda cfg, *keys, default=None: "smart" if keys[-1] == "cron_mode" else default
assert C._get_cron_approval_mode() == "smart", C._get_cron_approval_mode()
ctx = A._CRON_CTX
verdicts = {}
S._smart_verdict = lambda command, *a, **k: verdicts.get("v", "escalate")
dangerous = "rm -rf ~/work/jobs/applications/old-batch"
assert A.detect_dangerous_command(dangerous)[0], "test command should be flagged"
verdicts["v"] = "approve"
assert A._unattended_deny(dangerous, ctx) is None, "guardian approve -> allowed"
verdicts["v"] = "escalate"
r = A._unattended_deny(dangerous, ctx)
assert r and r["approved"] is False and "smart guardian did not approve" in r["message"], r
verdicts["v"] = "deny"
assert A._unattended_deny(dangerous, ctx)["approved"] is False
assert A._unattended_deny("ls -la /tmp", ctx) is None, "harmless command needs no verdict"

# verdict parsing: the last line decides; anything else escalates
from types import SimpleNamespace
import agent.auxiliary_client as X
for reply, want in [("APPROVE", "approve"), ("Read-only, routine.\n\nAPPROVE", "approve"), ("**DENY**", "deny"),
                    ("approve.", "approve"), ("APPROVE\nbut check first", "escalate"), ("This looks risky, ESCALATE", "escalate"),
                    ("", "escalate")]:
    X.call_llm = lambda *a, _r=reply, **k: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=_r), finish_reason="stop")])
    got = S._smart_approve("python3 -c 'print(1)'", "script execution via -e/-c flag")
    assert got == want, (reply, got, want)
print("smart-unattended patch test ok")
