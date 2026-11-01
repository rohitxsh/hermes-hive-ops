"""vault-guard (vm-b, 2026-10-28): the team's Bitwarden vault for the agents, through Hermes's own browser_vault tool.

Hermes fills logins model-blind (the password never reaches the conversation, the page origin must match the item),
but unlocks external password managers only through a masked terminal prompt, which Discord sessions don't have.
This plugin wraps browser_vault:
- unlock: Bitwarden is unlocked from sealed credentials (API key for the one-time `bw login`, master password for
  `bw unlock`) and synced. The session token lives only in Hermes's in-memory unlock store (30-min idle expiry) and
  is shared by every profile, because a second `bw unlock` would invalidate the first.
- permission: every fill and enter_code asks the people in the session's channel first, with the approve/decline
  button (request_elicitation_consent). Sessions where nobody can answer (cron, `chat -q`) are refused.
Every request is logged to ~/agents/vault-use.log (profile, item, username, site, action, decision; never secrets).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)
BW = os.path.expanduser("~/.local/bin/bw")
CREDS = "/etc/credstore.encrypted"
AUDIT = os.path.expanduser("~/agents/vault-use.log")
GUARDED = ("fill", "enter_code")
NOTE = (" On this VM every fill and enter_code first asks the people in this channel for permission (an approve/"
        "decline button); if it is declined, don't retry: say so and ask what they want instead.")


def _sealed(name: str) -> str:
    r = subprocess.run(["sudo", "-n", "systemd-creds", "decrypt", f"{CREDS}/{name}", "-"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"sealed credential {name} is missing")
    return r.stdout.strip()


def _bw(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    e = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.path.expanduser("~"), "NO_COLOR": "1",
         "BW_NOINTERACTION": "true", **(env or {})}
    return subprocess.run([BW, *args], capture_output=True, text=True, env=e, timeout=120, stdin=subprocess.DEVNULL)


def _bitwarden():
    from agent.vault_backends import enabled_backends
    return next((b for b in enabled_backends() if b.name == "bitwarden"), None)


def _share_live_token() -> bool:
    """Reuse another profile's live Bitwarden session for this profile instead of unlocking again."""
    from agent.vault_backends import unlock as u
    with u._lock:
        live = [(tok, last) for (home, backend), (tok, last) in u._sessions.items()
                if backend == "bitwarden" and time.monotonic() - last <= u._IDLE_TTL_S]
    return bool(live) and u.store_session_token("bitwarden", max(live, key=lambda x: x[1])[0])


def _ensure_unlocked() -> str | None:
    """None when Bitwarden is unlocked for this profile, else an error message."""
    b = _bitwarden()
    if b is None:
        return "Bitwarden isn't available here (bw CLI not found or vault.bitwarden disabled)"
    if b.is_unlocked() or _share_live_token():
        return None
    try:
        if json.loads(_bw("status").stdout or "{}").get("status") == "unauthenticated":
            r = _bw("login", "--apikey", env={"BW_CLIENTID": _sealed("bw_clientid"), "BW_CLIENTSECRET": _sealed("bw_clientsecret")})
            if r.returncode != 0:
                return "Bitwarden sign-in failed: " + (r.stderr or "").strip()[:160]
        master = _sealed("bw_master_password")
        try:
            b.unlock(master)
        finally:
            del master
        from agent.vault_backends import unlock as u
        _bw("sync", env={"BW_SESSION": u.get_session_token("bitwarden") or ""})  # items added since the last sync
    except Exception as exc:
        logger.warning("vault-guard: unlock failed: %s", exc)
        return f"Bitwarden unlock failed: {str(exc)[:160]}"
    return None


def _profile() -> str:
    from hermes_constants import get_hermes_home
    home = str(get_hermes_home()).rstrip("/")
    return "default" if home.endswith("/.hermes") else os.path.basename(home)


def _audit(**rec) -> None:
    try:
        with open(AUDIT, "a") as fh:
            fh.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "profile": _profile(), **rec}) + "\n")
    except OSError:
        pass


def _guarded(args: dict, **kwargs) -> str:
    from tools import browser_vault_tool as bv
    action = str(args.get("action") or "")
    if action in ("list", "unlock", *GUARDED):
        err = _ensure_unlocked()
        if err and action != "list":  # list still shows the local vault and reports Bitwarden as locked
            return json.dumps({"success": False, "error_type": "unlock_failed", "error": err})
    if action == "unlock":
        return json.dumps({"success": True, "backend": "bitwarden", "already_unlocked": True})
    if action in GUARDED:
        from agent.vault_backends import backend_for_handle
        from tools.approval_prompt import request_elicitation_consent
        handle = str(args.get("handle") or "")
        backend = backend_for_handle(handle)
        meta = backend.get_meta(handle) if backend is not None else None
        if meta is None:
            return bv._handle_vault(args, **kwargs)  # unknown handle: Hermes's own error, nothing to ask about
        what = "a 2FA code" if action == "enter_code" else "the password"
        site = meta.origin or "?"
        who = f" as {meta.identifier}" if meta.identifier else ""
        decision = request_elicitation_consent(
            f"{_profile()} wants to log in to {site}{who}, using the saved login '{meta.label}'",
            f"The agent will fill {what} from the vault on its own browser page ({site} only). It never sees the "
            "secret. Approve only if this login is expected.",
            surface="vault-login", title="Allow this vault login?")
        _audit(action=action, item=meta.label, username=meta.identifier, site=site, decision=decision)
        if decision != "accept":
            return json.dumps({"success": False, "error_type": "permission_declined",
                               "error": "Permission to use this login was not given. Don't retry; tell the channel "
                                        "and ask how to proceed."})
    return bv._handle_vault(args, **kwargs)


def register(ctx) -> None:
    from tools import browser_vault_tool as bv
    schema = dict(bv.BROWSER_VAULT_SCHEMA)
    schema["description"] = schema.get("description", "") + NOTE
    ctx.register_tool(name="browser_vault", toolset="browser", schema=schema, handler=_guarded,
                      check_fn=bv._check_vault_available, emoji="🔐", override=True)
