"""Give the software-team roles the kit's team skills (skills-team/ -> ~/agents/shared-skills-team) through
skills.external_dirs. Runs after apply-overlay.py, which resets external_dirs to the shared folder for everyone.
Targets: each team lead (a profile X with an X-dev sibling, like ops-core's @pm) and its X-dev, X-qa and X-devops
profiles; locked profiles are skipped. Idempotent; DRY=1 prints the plan. Run with Hermes's venv python.
--selftest checks the targeting."""
import glob
import os
import sys

TEAM_DIR = "~/agents/shared-skills-team"
ROLES = ("-dev", "-qa", "-devops")


def targets(names, locked=()):
    leads = {n for n in names if f"{n}-dev" in names}
    out = set(leads) | {f"{lead}{r}" for lead in leads for r in ROLES if f"{lead}{r}" in names}
    return sorted(out - set(locked))


def main():
    from ruamel.yaml import YAML
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    hh = os.path.expanduser("~/.hermes")
    names = [os.path.basename(p) for p in glob.glob(f"{hh}/profiles/*") if os.path.isfile(f"{p}/config.yaml")]
    locked = os.environ.get("LOCKED_PROFILES", "").split()
    dry = os.environ.get("DRY") == "1"
    for name in targets(names, locked):
        path = f"{hh}/profiles/{name}/config.yaml"
        cfg = yaml.load(open(path, encoding="utf-8"))
        skills = cfg.setdefault("skills", {})
        dirs = skills.get("external_dirs")
        if dirs is None:
            skills["external_dirs"] = dirs = []
        if TEAM_DIR in dirs:
            continue
        print(f"  {name}: + {TEAM_DIR}")
        if not dry:
            dirs.append(TEAM_DIR)
            with open(path, "w", encoding="utf-8") as fh:
                yaml.dump(cfg, fh)


def selftest():
    names = ["default", "random", "acme", "acme-dev", "acme-qa", "acme-devops", "acme-design", "solo", "solo-qa"]
    assert targets(names) == ["acme", "acme-dev", "acme-devops", "acme-qa"], targets(names)
    assert targets(names, locked=["acme-qa"]) == ["acme", "acme-dev", "acme-devops"]
    assert targets(["solo", "solo-qa"]) == []
    print("selftest ok")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
