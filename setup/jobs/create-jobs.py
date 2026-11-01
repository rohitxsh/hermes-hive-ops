"""Create the generic maintenance jobs from jobs.yaml in ADMIN_PROFILE. Skips jobs whose name already exists and
jobs whose `needs` file is missing. DRY=1 prints the plan."""
import json
import os
import subprocess

from ruamel.yaml import YAML

HERE = os.path.dirname(os.path.abspath(__file__))
HH = os.path.expanduser("~/.hermes")
DRY = os.environ.get("DRY") == "1"
ADMIN = os.environ.get("ADMIN_PROFILE") or "default"
DELIVER = os.environ.get("ADMIN_DELIVER") or "local"
HERMES = os.path.expanduser("~/.local/bin/hermes")
home = HH if ADMIN == "default" else f"{HH}/profiles/{ADMIN}"
existing = set()
if os.path.exists(f"{home}/cron/jobs.json"):
    d = json.load(open(f"{home}/cron/jobs.json"))
    existing = {j["name"] for j in (d["jobs"] if isinstance(d, dict) else d)}
for j in YAML(typ="safe").load(open(f"{HERE}/jobs.yaml")):
    if j["name"] in existing:
        print(f"{j['name']}: exists")
        continue
    if j.get("needs") and not os.path.exists(os.path.expanduser(j["needs"])):
        print(f"{j['name']}: skipped (needs {j['needs']})")
        continue
    deliver = DELIVER if j.get("deliver") == "admin" else j.get("deliver", "local")
    args = [HERMES] + ([] if ADMIN == "default" else ["-p", ADMIN]) + ["cron", "create", j["schedule"]]
    if j.get("prompt_file"):
        args.append(open(f"{HERE}/{j['prompt_file']}", encoding="utf-8").read().strip())
    args += ["--name", j["name"], "--deliver", deliver]
    if j.get("script"):
        args += ["--script", j["script"], "--no-agent"]
    if j.get("monitor_script"):
        args += ["--monitor-script", j["monitor_script"], "--failure-deliver", "local"]
    print(f"{j['name']}: " + ("would create" if DRY else "creating"))
    if not DRY:
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode:
            print(f"  ! failed: {(r.stderr or r.stdout).strip()[-200:]}")
