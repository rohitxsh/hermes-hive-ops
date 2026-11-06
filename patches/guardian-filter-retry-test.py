# offline test: first call blanked by a content filter, the fallback answers; no model is called
import sys; sys.path.insert(0, ".")
class N:
    def __init__(self, **kw): self.__dict__.update(kw)
import tools.approval  # same import order as the gateway
import tools.approval_smart as s
import hermes_cli.config as hc  # no real config or model: everything the guardian reads is stubbed
hc.load_config_readonly = lambda: {"fallback_providers": [{"provider": "fb", "model": "m"}]}
s._get_task_timeout = lambda task: 5
s._verdict_reasoning = lambda: None
s._get_smart_policy = lambda: ""
calls = []
def fake(**kw):
    calls.append(kw.get("provider"))
    if len(calls) == 1:
        return N(choices=[N(message=N(content=""), finish_reason="content_filter")])
    return N(choices=[N(message=N(content="APPROVE"), finish_reason="stop")])
import agent.auxiliary_client as ac
ac.call_llm = s.call_llm = fake
v = s._smart_approve("python3 -c \"print(1)\"", "script execution via -c flag")
assert v == "approve" and len(calls) == 2 and calls[1], (v, calls)
calls.clear()
def blank(**kw):
    calls.append(kw.get("provider")); return N(choices=[N(message=N(content=""), finish_reason="length")])
ac.call_llm = s.call_llm = blank
assert s._smart_approve("python3 -c \"print(1)\"", "x") == "escalate" and len(calls) == 1
print("guardian-filter-retry test ok", calls)
