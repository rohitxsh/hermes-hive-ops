"""Install vault-guard in every vm-b profile (2026-10-28). Run with /usr/bin/python3 on vm-b."""
import glob
import os
import shutil

import yaml

H = os.path.expanduser("~")
SRC = f"{H}/agents/src/vault-guard"
TAG = ".bak-2026-10-28-vault"
DENY = ["*bw get*", "*bw list*", "*bw unlock*", "*bw login*", "*bw export*", "*bw serve*", "*bw.js*",
        "*bitwarden-cli*", "*Bitwarden CLI*", "*BW_SESSION*", "*bw_master_password*", "*bw_clientid*",
        "*bw_clientsecret*", "*vault-use.log*"]

for home in [f"{H}/.hermes"] + sorted(glob.glob(f"{H}/.hermes/profiles/team*")):
    dst = f"{home}/plugins/vault-guard"
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(SRC, dst)
    cfg = f"{home}/config.yaml"
    if not os.path.exists(cfg + TAG):
        shutil.copy2(cfg, cfg + TAG)
    c = yaml.safe_load(open(cfg))
    pl = c.setdefault("plugins", {})
    en = pl.setdefault("enabled", []) or []
    if "vault-guard" not in en:
        en.append("vault-guard")
    pl["enabled"] = en
    pl.setdefault("entries", {}).setdefault("vault-guard", {})["allow_tool_override"] = True
    v = c.setdefault("vault", {})
    v.setdefault("bitwarden", {}).update(enabled=True, binary_path=f"{H}/.local/bin/bw")
    v.setdefault("onepassword", {})["enabled"] = False
    ap = c.setdefault("approvals", {})
    ap["deny"] = list(ap.get("deny") or []) + [d for d in DENY if d not in (ap.get("deny") or [])]
    yaml.safe_dump(c, open(cfg, "w"), sort_keys=False, width=200, allow_unicode=True)
    print(os.path.basename(home), "ok, deny rules:", len(ap["deny"]))
