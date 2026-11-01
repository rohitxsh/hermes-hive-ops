#!/usr/bin/python3
"""Local Hermes patch (2026-10-31, the owner asked about project card t_example): Kanban's PR acceptance gate reads the branch's
rulesets with `gh api repos/<repo>/rules/branches/<branch>`. On a private repo on a free GitHub plan that endpoint answers
HTTP 403 "Upgrade to GitHub Pro or make this repository public", which the gate treated as "this login can't see the repo"
and refused completion. Rulesets can't exist on such a repo, so the patch reads that answer as "no rulesets" and the gate
carries on with branch protection (also unavailable there, so: no required checks). Other 401/403/404s still block.
Idempotent; `--check` only reports. Lives in ~/agents/src/hermes-local-patches/; re-run after `hermes update` if the
self-check says it's missing, then restart the gateway when idle. Self-test: `--test` with Hermes's venv python."""
import shutil
import sys
from pathlib import Path

F = Path.home() / ".hermes/hermes-agent/hermes_cli/kanban_pr_acceptance.py"
TAG = ".bak-2026-10-31-rulesplan"
MARK = "local patch (2026-10-31): rulesets plan 403"
PAIRS = [
    ("        denied = re.search(r\"HTTP (40[134])\", exc.stderr or \"\")\n",
     f"        # {MARK}: a private repo on a free plan has no rulesets; GitHub says so with a 403\n"
     "        if \"Upgrade to GitHub Pro\" in (exc.stderr or \"\"):\n"
     "            raise _GatePlanRestricted(f\"HTTP 403 (plan) on {endpoint.split('?')[0]}\") from None\n"
     "        denied = re.search(r\"HTTP (40[134])\", exc.stderr or \"\")\n"),
    ("class _GateAuthError(RuntimeError):\n",
     "class _GatePlanRestricted(RuntimeError):\n"
     "    \"\"\"GitHub refused a feature the repository's plan doesn't include (rulesets on a private free-plan repo).\"\"\"\n\n\n"
     "class _GateAuthError(RuntimeError):\n"),
    ("        rules = _api(f\"repos/{repo}/rules/branches/{quote(branch, safe='')}?per_page=100\",\n"
     "                     paginate=True, profile_home=profile_home)\n",
     "        try:\n"
     "            rules = _api(f\"repos/{repo}/rules/branches/{quote(branch, safe='')}?per_page=100\",\n"
     "                         paginate=True, profile_home=profile_home)\n"
     "        except _GatePlanRestricted:\n"
     "            rules = []  # rulesets can't exist on this plan, so none require anything\n"
     "            receipt[\"rulesets\"] = \"unavailable on this GitHub plan (private repository); none apply\"\n"),
]


def selftest():
    sys.path.insert(0, str(F.parent.parent))
    import subprocess
    from unittest import mock
    import hermes_cli.kanban_pr_acceptance as m
    err = subprocess.CalledProcessError(1, "gh", stderr="gh: Upgrade to GitHub Pro or make this repository public to "
                                                       "enable this feature. (HTTP 403)")
    with mock.patch.object(m.subprocess, "run", side_effect=err):
        try:
            m._api("repos/o/r/rules/branches/main")
            raise AssertionError("no exception")
        except m._GatePlanRestricted:
            pass
    other = subprocess.CalledProcessError(1, "gh", stderr="gh: Resource not accessible (HTTP 403)")
    with mock.patch.object(m.subprocess, "run", side_effect=other):
        try:
            m._api("repos/o/r/pulls")
            raise AssertionError("no exception")
        except m._GateAuthError:
            pass  # an ordinary 403 still blocks as an identity problem
    graphql = {"data": {"repository": {"pullRequest": {"headRefOid": "a" * 40, "baseRefName": "main", "state": "OPEN",
                                                       "baseRef": {"branchProtectionRule": None}}}}}

    def fake(endpoint, **kw):
        if endpoint == "graphql":
            return graphql
        if "/rules/branches/" in endpoint:
            raise m._GatePlanRestricted("HTTP 403 (plan)")
        raise AssertionError("unexpected call " + endpoint)
    with mock.patch.object(m, "_api", side_effect=fake):
        r = m.collect_acceptance("https://github.com/o/r/pull/7", "https://github.com/o/r/pull/7")
    assert r.get("rulesets", "").startswith("unavailable"), r
    assert "No repository-required checks" in r.get("detail", ""), r
    print("selftest ok")


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
