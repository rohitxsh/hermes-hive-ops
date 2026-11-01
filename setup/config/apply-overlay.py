"""Merge overlay.yaml into every profile's config.yaml (locked.yaml on top for LOCKED_PROFILES). Keeps comments
(ruamel), backs up each config once (config.yaml.bak-kit), prints what changed. Run with Hermes's venv python.
DRY=1 prints the changes without writing."""
import copy
import glob
import os
import shutil
import sys

from ruamel.yaml import YAML

HERE = os.path.dirname(os.path.abspath(__file__))
HH = os.path.expanduser("~/.hermes")
DRY = os.environ.get("DRY") == "1"
LOCKED = set(os.environ.get("LOCKED_PROFILES", "").split())
yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096


def merge(dst, src, path=""):
    changed = []
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            changed += merge(dst[k], v, f"{path}{k}.")
        elif dst.get(k) != v:
            dst[k] = copy.deepcopy(v)
            changed.append(f"{path}{k}")
    return changed


def expand(v):
    return os.path.expanduser(v) if isinstance(v, str) and v.startswith("~/") else v


base = yaml.load(open(f"{HERE}/overlay.yaml"))
locked = yaml.load(open(f"{HERE}/locked.yaml"))
base["secrets"]["command"]["command"] = expand(base["secrets"]["command"]["command"])
profiles = [("default", HH)] + [(os.path.basename(d), d) for d in sorted(glob.glob(f"{HH}/profiles/*")) if os.path.isfile(f"{d}/config.yaml")]
for name, home in profiles:
    p = f"{home}/config.yaml"
    cfg = yaml.load(open(p)) or {}
    changed = merge(cfg, base)
    if name in LOCKED:
        changed += merge(cfg, locked)
    print(f"{name}: {len(set(changed))} setting(s) " + ("would change" if DRY else "changed") + (f" ({', '.join(sorted(set(changed))[:8])}...)" if changed else ""))
    if changed and not DRY:
        if not os.path.exists(p + ".bak-kit"):
            shutil.copy2(p, p + ".bak-kit")
        with open(p, "w") as fh:
            yaml.dump(cfg, fh)
if not DRY:
    print("Set SEARXNG_URL in each profile's .env if you use searxng-tuned, then restart the gateway.", file=sys.stderr)
