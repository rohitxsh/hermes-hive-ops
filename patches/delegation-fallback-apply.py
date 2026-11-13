#!/usr/bin/python3
"""Local Hermes patch (2026-11-13): delegation routes whose primary provider can't be resolved at spawn time (for
example Codex with its quota exhausted: resolve_runtime_provider raises "quota exhausted (429)") refused the whole
delegate_task call, although the route declares fallback_providers (Claude). Upstream only uses that chain for API
errors once the child runs. This patch makes tools/delegate_tool_routes._resolve_route try the route's own
fallback_providers entries, in order, as the child's primary when the configured primary fails to resolve
(ValueError from credential resolution only); the rest of the chain stays the child's fallback. Profile routes and
routes without a chain are unchanged; if every entry fails, the original error is raised.
Idempotent; `--check` only reports; `--test` runs the self-test with Hermes's venv python. Re-run after
`hermes update` if the self-check says it's missing."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "tools/delegate_tool_routes.py"
TAG = ".bak-2026-11-13-delegation-fallback"
MARK = "local patch (2026-11-13): delegation primary unresolvable -> route fallback"

A1 = ("    from tools.delegate_tool import _resolve_delegation_credentials  # the facade is the patch seam\n"
      "    creds = _resolve_delegation_credentials(route, parent_agent)\n")
B1 = ("    from tools.delegate_tool import _resolve_delegation_credentials  # the facade is the patch seam\n"
      f"    creds, route = _resolve_with_route_fallback(route, parent_agent, _resolve_delegation_credentials)  # {MARK}\n")
H = f'''

_ROUTE_ENDPOINT_KEYS = ("provider", "model", "base_url", "api_key", "api_mode")


def _resolve_with_route_fallback(route, parent_agent, resolve):
    """{MARK}: resolve the route's primary; when that raises ValueError (provider unusable, e.g. quota exhausted),
    start the child on the first resolvable fallback_providers entry instead, keeping the remaining entries as its
    fallback chain. Returns (creds, effective_route). Re-raises the original error when nothing resolves."""
    try:
        return resolve(route, parent_agent), route
    except ValueError as first:
        chain = route.get("fallback_providers")
        if route.get("profile") or not isinstance(chain, list) or not chain:
            raise
        for i, fb in enumerate(chain):
            if not isinstance(fb, dict) or not fb.get("provider"):
                continue
            alt = {{k: v for k, v in route.items() if k not in _ROUTE_ENDPOINT_KEYS}}
            alt.update({{k: fb[k] for k in _ROUTE_ENDPOINT_KEYS if fb.get(k)}})
            alt["fallback_providers"] = chain[i + 1:]
            try:
                creds = resolve(alt, parent_agent)
            except ValueError:
                continue
            logger.warning("delegation route %r: primary %s unavailable (%s); starting child on fallback %s/%s",
                           route.get("name") or route.get("label") or "default", route.get("provider"),
                           str(first)[:160], fb.get("provider"), fb.get("model"))
            return creds, alt
        raise
'''


def selftest():
    sys.path.insert(0, str(ROOT))
    from tools import delegate_tool_routes as r
    f = r._resolve_with_route_fallback

    def resolver(bad):
        def res(route, _p):
            if route.get("provider") in bad:
                raise ValueError(f"Cannot resolve delegation provider '{route['provider']}': quota exhausted (429)")
            return {"provider": route["provider"], "model": route.get("model")}
        return res

    fb = [{"provider": "claude", "model": "sonnet"}, {"provider": "other", "model": "m2"}]
    route = {"name": "standard", "provider": "openai-codex", "model": "gpt", "reasoning_effort": "medium",
             "fallback_providers": fb}
    creds, eff = f(route, None, resolver(set()))            # healthy primary: unchanged
    assert creds["provider"] == "openai-codex" and eff is route
    creds, eff = f(route, None, resolver({"openai-codex"}))  # exhausted primary -> first fallback
    assert creds == {"provider": "claude", "model": "sonnet"}
    assert eff["reasoning_effort"] == "medium" and eff["fallback_providers"] == fb[1:] and eff["name"] == "standard"
    assert route["provider"] == "openai-codex"               # original route not mutated
    creds, eff = f(route, None, resolver({"openai-codex", "claude"}))  # skips a failing fallback
    assert creds["provider"] == "other" and eff["fallback_providers"] == []
    for bad_route in ({**route, "fallback_providers": []}, {**route, "fallback_providers": None},
                      {**route, "profile": "x"}):
        try:
            f(bad_route, None, resolver({"openai-codex"}))
            raise AssertionError("expected original error")
        except ValueError as e:
            assert "openai-codex" in str(e)
    try:                                                     # everything fails -> original error
        f(route, None, resolver({"openai-codex", "claude", "other"}))
        raise AssertionError("expected original error")
    except ValueError as e:
        assert "openai-codex" in str(e)
    def boom(route, _p):                                     # non-ValueError is not swallowed
        raise RuntimeError("unexpected")
    try:
        f(route, None, boom)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
    print("selftest ok 9 cases")


s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    ok = MARK in s
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in s:
    assert s.count(A1) == 1, "delegate_tool_routes.py anchor not found once; upstream changed, patch by hand"
    s = s.replace(A1, B1).rstrip("\n") + "\n" + H
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
