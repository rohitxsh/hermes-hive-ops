"""vault-guard self-test: shared Bitwarden session vs Hermes revocations. Synthetic tokens and a fake `bw`; no vault,
no secrets. Run with Hermes's venv python from the Hermes checkout:
    cd ~/.hermes/hermes-agent && <venv>/bin/python ~/.hermes/plugins/vault-guard/selftest.py
Checks a plain share, then Lock (sharing and owning profile), owner-session release and shutdown landing before,
during and after a share, plus `bw` reporting locked and the idle expiry."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")
spec = importlib.util.spec_from_file_location("vg", Path(__file__).with_name("__init__.py"))
vg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vg)
from agent.vault_backends import unlock as u
import hermes_constants as hc

assert vg._REVOCABLE, "revocation hook did not attach"
A, B = tempfile.mkdtemp(), tempfile.mkdtemp()
cur = {"h": A}
hc.get_hermes_home = lambda: Path(cur["h"])
state = {"s": "unlocked", "during": None}


def fake_bw(*a, env=None):
    if state["during"]:  # a revocation landing while bw status runs
        state.pop("during")()
        state["during"] = None
    return subprocess.CompletedProcess(a, 0, json.dumps({"status": state["s"]}), "")


vg._bw = fake_bw


def in_home(h, f):
    def run():
        old, cur["h"] = cur["h"], h
        try:
            f()
        finally:
            cur["h"] = old
    return run


def reset_and_unlock_a():
    u.lock_all_profiles()
    u.set_current_session_id("S1")
    cur["h"] = A
    u.store_session_token("bitwarden", "SYNTHETIC")
    vg._remember()
    u.set_current_session_id("S2")
    cur["h"] = B


def shared_to_b():
    return vg._share_live_token() or u.is_unlocked("bitwarden")


reset_and_unlock_a()
assert shared_to_b() and u.get_session_token("bitwarden") == "SYNTHETIC", "plain share"
revocations = {
    "lock A": in_home(A, lambda: u.lock("bitwarden")),
    "lock B": lambda: u.lock("bitwarden"),
    "owner-session release": lambda: u.release_session("S1"),
    "shutdown": u.lock_all_profiles,
}
for name, revoke in revocations.items():
    reset_and_unlock_a()
    revoke()
    assert not shared_to_b(), f"before: {name}"
    reset_and_unlock_a()
    state["during"] = revoke
    assert not shared_to_b(), f"during: {name} restored a revoked token"
    reset_and_unlock_a()
    assert shared_to_b()
    revoke()
    if name != "lock A":  # A's own Lock leaves B's separately held token, as Hermes's per-profile Lock does
        assert not u.is_unlocked("bitwarden"), f"after: {name}"
    assert not vg._shared, f"after: {name} left the shared copy"
reset_and_unlock_a()
state["s"] = "locked"
assert not shared_to_b() and not vg._shared, "bw locked"
state["s"] = "unlocked"
reset_and_unlock_a()
vg._shared["at"] = time.monotonic() - vg.IDLE_TTL_S - 1
assert not shared_to_b() and not vg._shared, "idle expiry"


class Ctx:  # register() must find Hermes's own handler through the public registry and override with ours
    def register_tool(self, **kw):
        self.kw = kw


from tools import browser_vault_tool as bv
ctx = Ctx()
vg.register(ctx)
assert ctx.kw["handler"] is vg._guarded and ctx.kw["override"] is True
assert vg._BUILTIN["handler"] is bv._handle_vault, "captured handler is not Hermes's own"
assert vg._guarded.vault_guard_builtin is bv._handle_vault
print("selftest ok")
