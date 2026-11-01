"""Shared quota logic for the quota governor, `quota-status`, `automode` and the quota-alert plugin.

Each profile's model chain is read from its own config.yaml on every call (model.provider, then
fallback_providers in order), so model and fallback changes are picked up without code changes.

Policy (owner's rules, 2026-10-25):
- The first two providers in a chain are fine to work on; scheduled work pauses only when it would
  land on the third (both first and second used up).
- A profile in auto mode may use the first provider fully, but pauses once the second provider's
  5-hour window reaches AUTO_CAP percent or any of its weekly windows reaches WEEKLY_CAP percent.
  Claude Code CLI shares the Claude limit, so in auto mode Claude Code runs are gated at the same caps.
- The same caps apply permanently to a profile whose home has quota-caps.json {"always_auto_caps": true} (jobs,
  owner 2026-10-26), whether or not its auto mode is on (`caps()`). Its "cap_providers" list (e.g. ["claude"]) also caps
  those providers wherever they sit in the chain: when the provider that would answer is one of them and has reached a
  cap, scheduled work pauses (for example a profile whose chain starts with Claude).
- Before a pause, work gets a wrap-up warning: once the profile is within WRAP_MARGIN points of the point
  where it would pause, `quota-status --gate` says "wrap up" so runs finish their step and save a handoff.
Nothing here is tied to particular providers: rules follow chain positions (first, second, third).
Usage is read for providers that report it (ChatGPT/Codex and Claude subscriptions today; add a reader in
`usage()` for others). Any provider, readable or not, counts as used up in a profile for FAIL_WINDOW after
Hermes gave up on it there (all retries failed, or the fallback couldn't start it, e.g. no login in that
profile), so API-key and credit providers are covered too. Usage that can't be read and shows no recent
failure counts as available.
"""
import datetime
import glob
import json
import os
import re
import subprocess
import time

HOME = os.path.expanduser("~")
HERMES_DIR = os.path.join(HOME, ".hermes")
HERMES = os.path.join(HOME, ".local", "bin", "hermes")
CACHE = os.path.join(HERMES_DIR, "quota-cache.json")
CACHE_TTL = 240          # seconds a usage reading is reused
AUTO_CAP = 70.0          # % of the second provider's 5-hour window that auto mode may use
WEEKLY_CAP = 80.0        # % of the second provider's weekly windows that auto mode may use
WRAP_MARGIN = 10.0       # points before a pause point at which scheduled work is told to wrap up
FAIL_WINDOW = 3600       # seconds a provider Hermes gave up on in a profile counts as used up there
EXHAUSTED = 99.5         # a window at or above this is used up
AUTO_FILE = "auto-mode.json"
AUTO_JOB = "Auto mode"
CLAUDE_PLUGIN = os.path.join(HERMES_DIR, "plugins", "claude-subscription-directsdk-experimental")
NAMES = {"openai-codex": "ChatGPT (Codex)", "nous": "Nous", "openrouter": "OpenRouter"}


def provider_name(provider):
    if provider and provider.startswith("claude"):
        return "Claude"
    return NAMES.get(provider, provider or "?")


def is_claude(provider):
    return bool(provider) and provider.startswith("claude")


# ---------- profiles, chains, auto mode ----------

def profiles():
    yield "default", HERMES_DIR
    for home in sorted(glob.glob(os.path.join(HERMES_DIR, "profiles", "*"))):
        if os.path.isfile(os.path.join(home, "config.yaml")):
            yield os.path.basename(home), home


def profile_home(name):
    return HERMES_DIR if name in ("default", "", None) else os.path.join(HERMES_DIR, "profiles", name)


def current_profile():
    home = os.path.realpath(os.environ.get("HERMES_HOME") or HERMES_DIR)
    return "default" if home == os.path.realpath(HERMES_DIR) else os.path.basename(home)


def load_config(home):
    import yaml
    with open(os.path.join(home, "config.yaml")) as fh:
        return yaml.safe_load(fh) or {}


def chain(home=None, cfg=None):
    cfg = cfg if cfg is not None else load_config(home)
    out = []
    for p in [(cfg.get("model") or {}).get("provider")] + [f.get("provider") for f in cfg.get("fallback_providers") or []]:
        if p and p not in out:
            out.append(p)
    return out


GOV_STATE = os.path.join(HERMES_DIR, "quota-guard.json")


def load_gov_state():
    """The governor's record of what it paused (shared with `automode`)."""
    try:
        with open(GOV_STATE) as fh:
            s = json.load(fh)
    except (OSError, ValueError):
        s = {}
    paused = s.get("paused", {})
    if isinstance(paused, list):  # first version kept a list of {profile, id, name}
        paused = {f"{j['profile']}:{j['id']}": j for j in paused}
    return {"paused": paused, "kanban_blocked": s.get("kanban_blocked", []), "kanban_allowed": s.get("kanban_allowed"),
            "wrapping": s.get("wrapping", [])}


def save_gov_state(state):
    tmp = GOV_STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, GOV_STATE)


def auto_mode(home):
    try:
        with open(os.path.join(home, AUTO_FILE)) as fh:
            return bool(json.load(fh).get("enabled"))
    except (OSError, ValueError):
        return False


CAPS_FILE = "quota-caps.json"


def caps_always(home):
    """True when the owner made the auto-mode caps permanent for this profile (<home>/quota-caps.json)."""
    try:
        with open(os.path.join(home, CAPS_FILE)) as fh:
            return bool(json.load(fh).get("always_auto_caps"))
    except (OSError, ValueError):
        return False


def caps(home):
    """Whether the auto-mode caps apply to this profile: auto mode is on, or the caps are always on."""
    return auto_mode(home) or caps_always(home)


def cap_providers(home):
    """Providers the owner capped wherever they sit in this profile's chain ("cap_providers" in quota-caps.json)."""
    try:
        with open(os.path.join(home, CAPS_FILE)) as fh:
            return tuple(str(p) for p in json.load(fh).get("cap_providers") or ())
    except (OSError, ValueError):
        return ()


def _named(provider, names):
    return any(provider == n or (n == "claude" and is_claude(provider)) for n in names)


# ---------- usage readers ----------

def _window(label, used, resets_at):
    return {"label": label, "used": float(used), "resets_at": resets_at}


def pool_windows(auth, now):
    """Codex credential pool record: one 100% window while every login is out of quota."""
    entries = (auth.get("credential_pool") or {}).get("openai-codex") or []
    resets = [e.get("last_error_reset_at") or 0 for e in entries
              if e.get("last_status") == "exhausted" and (e.get("last_error_reset_at") or 0) > now]
    if entries and len(resets) == len(entries):
        iso = datetime.datetime.fromtimestamp(min(resets), datetime.timezone.utc).isoformat()
        return [_window("limit", 100.0, iso)]
    return [_window("limit", 0.0, None)] if entries else None


def codex_from_snapshot_windows(windows):
    """Hermes usage windows ('Session', 'Weekly') -> our shape ('5-hour', 'weekly')."""
    label = {"session": "5-hour", "weekly": "weekly"}
    return [_window(label.get(str(w.get("label", "")).lower(), str(w.get("label", ""))), w["used_percent"], w.get("resets_at"))
            for w in windows if w.get("used_percent") is not None]


def _read_codex():
    try:
        out = subprocess.run([HERMES, "usage", "--provider", "openai-codex", "--json"],
                             capture_output=True, text=True, timeout=90).stdout
        windows = codex_from_snapshot_windows(json.loads(out[out.index("{"):]).get("windows") or [])
        if windows:
            return windows
    except (ValueError, OSError, subprocess.SubprocessError):
        pass
    try:  # a pool-only login can't be read while rate-limited; the pool records the limit itself
        with open(os.path.join(HERMES_DIR, "auth.json")) as fh:
            return pool_windows(json.load(fh), time.time())
    except (OSError, ValueError):
        return None


_CLAUDE_SNIPPET = r"""
import json, os, sys
sys.path.insert(0, sys.argv[1])
import directsdk_setup as d
# Claude Code reports plan usage only with nonessential traffic on; keep telemetry and error reports off.
d.QUIET_TRAFFIC = {"DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1"}
env = dict(os.environ, CLAUDE_CONFIG_DIR=os.path.expanduser("~/.claude"))
limits, reason = d.fetch_usage(env=env, timeout=30)
print(json.dumps({"limits": limits, "reason": reason}))
"""


def claude_windows_from_limits(limits):
    names = (("five_hour", "5-hour"), ("seven_day", "weekly"), ("seven_day_opus", "Opus weekly"),
             ("seven_day_sonnet", "Sonnet weekly"))
    out = []
    for key, label in names:
        w = limits.get(key)
        if isinstance(w, dict) and isinstance(w.get("utilization"), (int, float)):
            u = float(w["utilization"])
            out.append(_window(label, u * 100.0 if u <= 1 and isinstance(w["utilization"], float) else u, w.get("resets_at")))
    return out


def _read_claude():
    if not os.path.isdir(CLAUDE_PLUGIN):
        return None
    env = dict(os.environ, PATH=os.path.join(HOME, ".local", "bin") + ":" + os.environ.get("PATH", "/usr/bin:/bin"))
    env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)
    try:
        r = subprocess.run(["/usr/bin/python3", "-c", _CLAUDE_SNIPPET, CLAUDE_PLUGIN],
                           capture_output=True, text=True, timeout=90, env=env)
        data = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError, OSError, subprocess.SubprocessError):
        return None
    return claude_windows_from_limits(data["limits"]) if isinstance(data.get("limits"), dict) else None


def _load_cache():
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cache, fh)
    os.replace(tmp, CACHE)


def usage(provider, fresh=False, allow_fetch=True):
    """Windows [{label, used, resets_at}] for a provider, or None when unknown. Cached CACHE_TTL s."""
    key = "claude" if is_claude(provider) else provider
    cache = _load_cache()
    hit = cache.get(key)
    if hit and not fresh and time.time() - hit.get("at", 0) < CACHE_TTL:
        return hit.get("windows")
    if not allow_fetch:
        return hit.get("windows") if hit and time.time() - hit.get("at", 0) < 3 * CACHE_TTL else None
    reader = _read_codex if key == "openai-codex" else _read_claude if key == "claude" else None
    if reader is None:
        return None
    windows = reader()
    cache = _load_cache()
    cache[key] = {"at": time.time(), "windows": windows}
    try:
        _save_cache(cache)
    except OSError:
        pass
    return windows


# ---------- decisions ----------

def used_up(windows):
    return [w for w in windows or [] if w["used"] >= EXHAUSTED]


def five_hour(windows):
    return next((w for w in windows or [] if w["label"] == "5-hour"), None)


def auto_cap(provider, windows):
    """Why auto mode must stop on this (second) provider, or "" while it is under both caps."""
    w = five_hour(windows)
    if w and w["used"] >= AUTO_CAP:
        return (f"{provider_name(provider)}'s 5-hour window is at {w['used']:.0f}% (auto-mode cap {AUTO_CAP:.0f}%), "
                f"resets {local_time(w['resets_at'])}")
    for w in windows or []:
        if w["label"].endswith("weekly") and w["used"] >= WEEKLY_CAP:
            return (f"{provider_name(provider)}'s {w['label']} limit is at {w['used']:.0f}% (auto-mode cap {WEEKLY_CAP:.0f}%), "
                    f"resets {local_time(w['resets_at'])}")
    return ""


def active_index(providers, getu):
    """Index of the first provider in the chain that isn't used up (unknown counts as available)."""
    for i, p in enumerate(providers):
        if not used_up(getu(p)):
            return i
    return len(providers)


def local_time(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().strftime("%a %H:%M")
    except (TypeError, ValueError):
        return "unknown"


def describe(windows):
    if windows is None:
        return "usage unknown"
    if windows and windows[0]["label"] == "failing":
        return f"failing in this profile (Hermes gave up on it; retried after {local_time(windows[0]['resets_at'])})"
    return ", ".join(f"{w['label']} {w['used']:.0f}% used" + (f" (resets {local_time(w['resets_at'])})" if w.get("resets_at") else "")
                     for w in windows) or "no limits reported"


def run_allowed(providers, auto, getu, capped=()):
    """(allowed, reason) for scheduled work of a profile. ``capped``: providers capped wherever they are (auto caps on)."""
    if not providers:
        return True, ""
    i = active_index(providers, getu)
    if auto and i < len(providers) and _named(providers[i], capped):
        why = auto_cap(providers[i], getu(providers[i]))
        if why:
            return False, f"{why} (capped for this profile)"
    if i >= 2:
        return False, (f"{provider_name(providers[0])} and {provider_name(providers[1])} are both used up "
                       f"({describe(getu(providers[0]))}; {describe(getu(providers[1]))})" if len(providers) > 1
                       else f"{provider_name(providers[0])} is used up ({describe(getu(providers[0]))})")
    if auto and i == 1:
        why = auto_cap(providers[1], getu(providers[1]))
        if why:
            return False, f"{provider_name(providers[0])} is used up and {why}"
    return True, ""


def claude_code_allowed(auto, getu):
    """Claude Code CLI shares the Claude limit: capped at AUTO_CAP / WEEKLY_CAP in auto mode, else until used up."""
    windows = getu("claude")
    if used_up(windows):
        return False, f"Claude is used up ({describe(windows)})"
    why = auto_cap("claude", windows) if auto else ""
    near = [w for w in windows or [] if w["used"] >= EXHAUSTED - WRAP_MARGIN]
    if not why and near:  # a run started this close to the limit would likely be cut off mid-way
        why = (f"Claude's {near[0]['label']} limit is at {near[0]['used']:.0f}%, too close to the limit to start a run, "
               f"resets {local_time(near[0]['resets_at'])}")
    return (False, why) if why else (True, "")


_FAIL = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .*?(?:Fallback to (\S+) failed|API call failed after \d+ retries\..*\| provider=(\S+))")


def recent_failures(home, now=None):
    """{provider: time} of providers Hermes gave up on in this profile within FAIL_WINDOW (from its agent.log)."""
    now = now or time.time()
    path = os.path.join(home, "logs", "agent.log")
    try:
        with open(path, "rb") as fh:
            fh.seek(max(0, os.path.getsize(path) - 1_000_000))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return {}
    out = {}
    for line in lines:
        m = _FAIL.match(line)
        if m:
            t = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
            if now - t < FAIL_WINDOW:
                p = m.group(2) or m.group(3)
                out[p] = max(out.get(p, 0.0), t)
    return out


def profile_usage(home, getu, now=None):
    """getu for one profile: a provider that failed there recently counts as used up until FAIL_WINDOW passes."""
    failed = recent_failures(home, now)

    def get(provider):
        if provider in failed:
            until = datetime.datetime.fromtimestamp(failed[provider] + FAIL_WINDOW, datetime.timezone.utc).isoformat()
            return [_window("failing", 100.0, until)]
        return getu(provider)
    return get


def wrap_up(providers, auto, getu, capped=()):
    """Why scheduled work should finish its current step and stop soon ("" if not): the profile is within
    WRAP_MARGIN points of the point where the governor pauses it."""
    if not providers or not run_allowed(providers, auto, getu, capped)[0]:
        return ""
    i, last = active_index(providers, getu), min(1, len(providers) - 1)
    if auto and i < len(providers) and _named(providers[i], capped):
        ws = getu(providers[i]) or []
        w = five_hour(ws)
        if w and w["used"] >= AUTO_CAP - WRAP_MARGIN:
            return f"{provider_name(providers[i])}'s 5-hour window is at {w['used']:.0f}% (this profile pauses at {AUTO_CAP:.0f}%)"
        w = next((w for w in ws if w["label"].endswith("weekly") and w["used"] >= WEEKLY_CAP - WRAP_MARGIN), None)
        if w:
            return f"{provider_name(providers[i])}'s {w['label']} limit is at {w['used']:.0f}% (this profile pauses at {WEEKLY_CAP:.0f}%)"

    def close(k):
        ws = getu(providers[k]) or []
        name = provider_name(providers[k])
        if auto and k == 1:
            w = five_hour(ws)
            if w and w["used"] >= AUTO_CAP - WRAP_MARGIN:
                return f"{name}'s 5-hour window is at {w['used']:.0f}% (auto mode pauses at {AUTO_CAP:.0f}%)"
            w = next((w for w in ws if w["label"].endswith("weekly") and w["used"] >= WEEKLY_CAP - WRAP_MARGIN), None)
            return f"{name}'s {w['label']} limit is at {w['used']:.0f}% (auto mode pauses at {WEEKLY_CAP:.0f}%)" if w else ""
        w = next((w for w in ws if w["used"] >= EXHAUSTED - WRAP_MARGIN), None)
        return f"{name}'s {w['label']} limit is at {w['used']:.0f}%" if w else ""

    if i == last:
        return close(i)
    if i == 0 and last == 1:  # on the first provider: only matters when the second can't take over
        second = getu(providers[1])
        if used_up(second) or (auto and auto_cap(providers[1], second)):
            why = close(0)
            return f"{why}, and {provider_name(providers[1])} can't take over" if why else ""
    return ""


def selftest():
    def fake(table):
        return lambda p: table.get("claude" if is_claude(p) else p)
    c = ["openai-codex", "claude-subscription-directsdk-experimental", "nous", "openrouter"]
    ok = [_window("5-hour", 10, None), _window("weekly", 20, None)]
    out5 = [_window("5-hour", 100, "2026-10-25T01:00:00+00:00"), _window("weekly", 50, None)]
    outw = [_window("5-hour", 3, None), _window("weekly", 100, "2026-10-30T18:00:00+00:00")]
    c71 = [_window("5-hour", 71, "2026-10-25T03:00:00+00:00"), _window("weekly", 20, None)]
    assert run_allowed(c, False, fake({"openai-codex": ok, "claude": ok})) == (True, "")
    assert run_allowed(c, False, fake({"openai-codex": out5, "claude": c71}))[0]      # second provider is fine to use
    assert not run_allowed(c, True, fake({"openai-codex": out5, "claude": c71}))[0]   # auto mode stops at 70%
    assert run_allowed(c, True, fake({"openai-codex": ok, "claude": c71}))[0]         # primary still fine
    assert not run_allowed(c, False, fake({"openai-codex": outw, "claude": out5}))[0] # weekly-out + Claude out: third tier
    assert run_allowed(c, True, fake({"openai-codex": outw, "claude": ok}))[0]        # weekly limit counts as used up
    assert run_allowed(c, True, fake({"openai-codex": out5}))[0]                      # Claude unknown -> allowed
    w81 = [_window("5-hour", 10, None), _window("weekly", 81, "2026-10-30T18:00:00+00:00")]
    opus81 = [_window("5-hour", 10, None), _window("weekly", 40, None), _window("Opus weekly", 81, None)]
    assert not run_allowed(c, True, fake({"openai-codex": out5, "claude": w81}))[0]   # auto mode stops at 80% weekly
    assert not run_allowed(c, True, fake({"openai-codex": out5, "claude": opus81}))[0]
    assert run_allowed(c, False, fake({"openai-codex": out5, "claude": w81}))[0]      # outside auto mode: no weekly cap
    assert run_allowed(c, True, fake({"openai-codex": ok, "claude": w81}))[0]         # caps only bite on the second provider
    assert not claude_code_allowed(True, fake({"claude": w81}))[0]
    assert claude_code_allowed(False, fake({"claude": w81}))[0]
    assert not claude_code_allowed(True, fake({"claude": c71}))[0]
    c92 = [_window("5-hour", 92, None), _window("weekly", 30, None)]
    c62 = [_window("5-hour", 62, None), _window("weekly", 30, None)]
    assert not claude_code_allowed(False, fake({"claude": c92}))[0]                 # too close to start a Claude Code run
    assert wrap_up(c, False, fake({"openai-codex": out5, "claude": c92}))           # last allowed provider nearly out
    assert not wrap_up(c, False, fake({"openai-codex": out5, "claude": c62}))
    assert wrap_up(c, True, fake({"openai-codex": out5, "claude": c62}))            # auto: near the 70% cap
    assert wrap_up(c, True, fake({"openai-codex": [_window("5-hour", 95, None)], "claude": c71}))  # primary nearly out, Claude capped
    assert not wrap_up(c, True, fake({"openai-codex": ok, "claude": c71}))
    assert not wrap_up(c, True, fake({"openai-codex": out5, "claude": c71}))        # already paused: no wrap-up
    import tempfile
    home = tempfile.mkdtemp()
    os.makedirs(os.path.join(home, "logs"))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(home, "logs", "agent.log"), "w") as fh:
        fh.write(f"{stamp},1 WARNING [x] agent.chat_completion_helpers: Fallback to openai-codex failed: provider not configured\n"
                 f"{stamp},2 ERROR [x] agent.conversation_loop: API call failed after 3 retries. HTTP 429: limit | provider=claude-x model=m\n"
                 "2020-01-01 00:00:00,0 ERROR agent.conversation_loop: API call failed after 3 retries. HTTP 402 | provider=nous model=m\n")
    assert set(recent_failures(home)) == {"openai-codex", "claude-x"}
    pu = profile_usage(home, fake({"claude": ok}))
    assert used_up(pu("openai-codex")) and not used_up(pu("claude-y"))
    assert not run_allowed(["claude-x", "openai-codex", "nous"], False, pu)[0]       # both failing here: pause before the third
    assert "failing in this profile" in describe(pu("openai-codex"))
    assert not caps(home)                                                      # no flags: caps follow auto mode
    with open(os.path.join(home, CAPS_FILE), "w") as fh:
        json.dump({"always_auto_caps": True}, fh)
    assert caps(home) and caps_always(home) and not auto_mode(home)            # permanent caps without auto mode
    fable = ["claude-subscription-directsdk-experimental", "openai-codex", "nous"]
    c75 = [_window("5-hour", 75, "2026-10-26T05:00:00+00:00"), _window("weekly", 30, None)]
    c50 = [_window("5-hour", 50, None), _window("weekly", 30, None)]
    w85 = [_window("5-hour", 20, None), _window("weekly", 85, None)]
    assert not run_allowed(fable, True, fake({"claude": c75, "openai-codex": ok}), ("claude",))[0]   # primary Claude capped
    assert not run_allowed(fable, True, fake({"claude": w85, "openai-codex": ok}), ("claude",))[0]   # weekly cap too
    assert run_allowed(fable, True, fake({"claude": c50, "openai-codex": ok}), ("claude",))[0]
    assert run_allowed(fable, True, fake({"claude": c75, "openai-codex": ok}))[0]                    # without cap_providers: old rule
    assert wrap_up(fable, True, fake({"claude": c62, "openai-codex": ok}), ("claude",))
    assert run_allowed(fable, False, fake({"claude": c75, "openai-codex": ok}), ("claude",))[0]      # caps off: no pause
    with open(os.path.join(home, CAPS_FILE), "w") as fh:
        json.dump({"always_auto_caps": True, "cap_providers": ["claude"]}, fh)
    assert cap_providers(home) == ("claude",)
    assert claude_code_allowed(False, fake({"claude": c71}))[0]
    assert active_index(c, fake({"openai-codex": outw})) == 1
    assert claude_windows_from_limits({"five_hour": {"utilization": 12, "resets_at": "x"}})[0]["used"] == 12.0
    assert claude_windows_from_limits({"five_hour": {"utilization": 0.5, "resets_at": "x"}})[0]["used"] == 50.0
    assert codex_from_snapshot_windows([{"label": "Session", "used_percent": 100.0}])[0]["label"] == "5-hour"
    exhausted_pool = {"credential_pool": {"openai-codex": [{"last_status": "exhausted", "last_error_reset_at": 2000.0}]}}
    assert pool_windows(exhausted_pool, 1000.0)[0]["used"] == 100.0
    assert pool_windows(exhausted_pool, 3000.0)[0]["used"] == 0.0
    assert chain(cfg={"model": {"provider": "a"}, "fallback_providers": [{"provider": "b"}, {"provider": "a"}]}) == ["a", "b"]
    print("quota_lib selftest ok")


if __name__ == "__main__":
    selftest()
