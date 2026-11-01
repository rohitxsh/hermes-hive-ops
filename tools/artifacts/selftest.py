#!/usr/bin/env python3
"""selftest.py <out.html>: writes a sample interactive chart built from live data on this VM
(disk used per Hermes profile, split into sessions / logs / skills / other)."""
import json, os, socket, subprocess, sys, datetime
H = os.path.expanduser("~/.hermes")
profiles = {"default": H}
pdir = os.path.join(H, "profiles")
for p in sorted(os.listdir(pdir)):
    if os.path.isdir(os.path.join(pdir, p)) and not p.startswith("."):
        profiles[p] = os.path.join(pdir, p)

def mb(path):
    if not os.path.exists(path):
        return 0.0
    out = subprocess.run(["du", "-sk", path], capture_output=True, text=True).stdout.split()
    return round(int(out[0]) / 1024, 1) if out else 0.0

parts = ["sessions", "logs", "skills"]
rows = []
for name, root in profiles.items():
    vals = {k: mb(os.path.join(root, k)) for k in parts}
    if name == "default":  # default's root also holds profiles/, installs and caches: count only its own parts
        vals["other"] = round(mb(os.path.join(root, "memories")) + mb(os.path.join(root, "cron")), 1)
    else:
        vals["other"] = round(max(0.0, mb(root) - sum(vals.values())), 1)
    rows.append({"profile": name, **vals})

stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>publish-artifact self-test</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.6.1/dist/chart.umd.min.js"></script>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#0f172a;color:#e2e8f0;font:15px/1.5 system-ui,sans-serif}
main{max-width:1160px;margin:0 auto;padding:28px 20px}h1{font-size:24px;margin:0 0 4px}
.lede,.src{color:#94a3b8}.src{font-size:12px}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}
button{background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:8px;padding:6px 12px;cursor:pointer}
button.on{border-color:#38bdf8;color:#38bdf8}
.card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px}.chart{position:relative;height:520px}
</style></head><body><main>
<h1>Disk used per Hermes profile (MB)</h1>
<p class="lede">publish-artifact self-test: live data from HOST. Click the toggles to show or hide each part; hover a bar for values.</p>
<div class="bar" id="toggles"></div>
<div class="card"><div class="chart"><canvas id="c"></canvas></div></div>
<p class="src">Source: du on ~/.hermes and ~/.hermes/profiles/*, STAMP. default counts only its own sessions, logs, skills, memories and cron.</p>
</main><script>
const rows = DATA;
const parts = ["sessions","logs","skills","other"], colors = ["#38bdf8","#f472b6","#a3e635","#fbbf24"];
Chart.defaults.color = "#cbd5e1"; Chart.defaults.borderColor = "#334155";
const chart = new Chart(document.getElementById("c"), {type:"bar",
  data:{labels:rows.map(r=>r.profile), datasets:parts.map((p,i)=>({label:p,data:rows.map(r=>r[p]),backgroundColor:colors[i]}))},
  options:{maintainAspectRatio:false,indexAxis:"y",scales:{x:{stacked:true,title:{display:true,text:"MB"}},y:{stacked:true}},
    plugins:{tooltip:{callbacks:{footer:items=>"total "+items.reduce((s,i)=>s+i.parsed.x,0).toFixed(1)+" MB"}}}}});
const t = document.getElementById("toggles");
parts.forEach((p,i)=>{const b=document.createElement("button");b.textContent=p;b.className="on";
  b.onclick=()=>{const v=chart.isDatasetVisible(i);chart.setDatasetVisibility(i,!v);b.classList.toggle("on",!v);chart.update();};t.appendChild(b);});
</script></body></html>"""
html = html.replace("DATA", json.dumps(rows)).replace("STAMP", stamp).replace("HOST", socket.gethostname())
with open(sys.argv[1], "w") as f:
    f.write(html)
print(len(rows), "profiles")
