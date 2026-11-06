# 2026-11-06 (the owner): Hermes's Supabase connector via OAuth (no token on disk): read-write for devops, read-only for
# dev, qa and architect, removed from profiles that don't touch the database. Cloudflare connector (OAuth) for devops.
# Fixed OAuth callback port 8765 so a login works headless through `ssh -L 8765:127.0.0.1:8765`. Idempotent.
# Run with Hermes's venv python. Change later: edit mcp_servers in the profile's config.yaml (add or drop
# `read_only=true` in the url, or delete the entry), then `hermes -p <profile> mcp login <name>` and an idle restart.
import glob, os, shutil
from ruamel.yaml import YAML
H = os.path.expanduser("~")
y = YAML(); y.preserve_quotes = True; y.width = 4096; y.indent(mapping=2, sequence=4, offset=2)
OAUTH = {"redirect_port": 8765}


def role(profile):
    for r in ("devops", "dev", "qa", "architect"):
        if profile.endswith("-" + r):
            return r
    return None


for c in sorted(glob.glob(f"{H}/.hermes/profiles/*/config.yaml")):
    prof = c.split("/")[-2]
    with open(c, encoding="utf-8") as fh:
        d = y.load(fh)
    mcp = d.get("mcp_servers") or {}
    sb = mcp.get("supabase")
    r = role(prof)
    changed = []
    if sb is not None:
        if r is None:
            del mcp["supabase"]; changed.append("supabase removed")
        else:
            url = str(sb.get("url", "https://mcp.supabase.com/mcp")).replace("&read_only=true", "").replace("?read_only=true", "")
            if r != "devops":
                url += ("&" if "?" in url else "?") + "read_only=true"
            new = {"url": url, "auth": "oauth", "oauth": dict(OAUTH)}
            if dict(sb) != new:
                mcp["supabase"] = new; changed.append("supabase " + ("read-write" if r == "devops" else "read-only") + " oauth")
    if r == "devops" and "cloudflare" not in mcp:
        mcp["cloudflare"] = {"url": "https://mcp.cloudflare.com/mcp", "auth": "oauth", "oauth": dict(OAUTH)}
        changed.append("cloudflare oauth added")
    if changed:
        shutil.copy2(c, c + ".bak-2026-11-06-mcp")
        with open(c, "w", encoding="utf-8") as fh:
            y.dump(d, fh)
        with open(c, encoding="utf-8") as fh:
            YAML(typ="safe").load(fh)
    print(prof, ", ".join(changed) or "unchanged")
