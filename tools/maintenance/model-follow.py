#!/usr/bin/env python3
"""Keep Hermes, Codex and Claude Code on the newest model of each family they already use.

For every model family in use it asks the provider which model is newest, checks that model answers, then rewrites
the old name everywhere it is configured. Families nobody uses are never adopted.
  Codex (openai-codex): newest listed slug per family (sol, terra, astra, luna) from the Codex CLI's cached model
    list for this ChatGPT account (~/.codex/models_cache.json); smoke: one `codex exec` call.
  OpenAI API (openai-api): newest per family from GET /v1/models with the sealed key; smoke: one tiny Responses call.
  Claude (subscription plugin, anthropic, Claude Code): what Claude Code's own alias (opus, sonnet, haiku, fable,
    mythos) resolves to in one `claude -p` call, which is also the smoke. A family whose alias call fails (no alias on
    this account, used-up window) stays pinned.
Rewritten: provider-scoped `model:`/`default:` values in ~/.hermes/config.yaml and every profile config, `model = `
lines in ~/.codex/config.toml, Claude names in those configs and ~/.claude/settings.json, and old names in the
ops-core rule files (shared and per-profile copies) and ~/agents/rules (then `hermes ops-rules apply`).
A model that does not answer (plan, rollout, no credit, used-up window) leaves its family unchanged until a later run.
Backups go to ~/agents/backups; switches are logged to ~/.local/state/cli-update.log and ~/agents/ADMIN-CHANGES.md,
then the gateway restarts when idle. Runs from cli-update. --dry-run lists what is in use and what is newest, without
smoke calls or writes; --selftest checks the parsing.
"""
import datetime, glob, json, os, re, shutil, subprocess, sys, tempfile, urllib.request
import yaml

H = os.path.expanduser("~")
os.environ["PATH"] = f"{H}/.local/bin:" + os.environ.get("PATH", "/usr/bin:/bin")  # codex/claude live here; ssh and cron lack it
GPT = re.compile(r"gpt-(\d+(?:\.\d+)*)-([a-z]+)")
CLAUDE = re.compile(r"claude-(opus|sonnet|haiku|fable|mythos)-(\d+)-(\d+)")


def scalars(node):
    """Every string value in a parsed YAML/JSON document (comments are not values)."""
    if isinstance(node, dict):
        for v in node.values():
            yield from scalars(v)
    elif isinstance(node, list):
        for v in node:
            yield from scalars(v)
    elif isinstance(node, str):
        yield node


def claude_names(doc):
    return {m[0] for s in scalars(doc) for m in [CLAUDE.match(s)] if m and s[m.end():] in ("", "[1m]")}


def gver(s):
    return tuple(int(x) for x in GPT.fullmatch(s)[1].split("."))


def newest_gpt(slugs):
    best = {}
    for s in slugs:
        g = GPT.fullmatch(s)
        if g and (g[2] not in best or gver(s) > gver(best[g[2]])):
            best[g[2]] = s
    return best


def cver(s):
    g = CLAUDE.fullmatch(s)
    return (int(g[2]), int(g[3]))


def yaml_values(text):
    """[(provider, line, col, value)] for model/default scalars in mappings that name a provider."""
    out = []

    def walk(n):
        if isinstance(n, yaml.MappingNode):
            kv = {k.value: v for k, v in n.value if isinstance(k, yaml.ScalarNode)}
            p = kv.get("provider")
            if isinstance(p, yaml.ScalarNode):
                for key in ("model", "default"):
                    v = kv.get(key)
                    if isinstance(v, yaml.ScalarNode) and v.value:
                        out.append((p.value, v.start_mark.line, v.start_mark.column, v.value))
            for _, v in n.value:
                walk(v)
        elif isinstance(n, yaml.SequenceNode):
            for v in n.value:
                walk(v)

    walk(yaml.compose(text))
    return out


def scope(provider):
    return {"openai-codex": "codex", "openai-api": "openai-api"}.get(provider)


def edit_yaml(text, moves):
    """GPT names change only under their own provider (Codex and the API list different models)."""
    lines = text.split("\n")
    for prov, ln, col, val in yaml_values(text):
        new = moves.get(scope(prov), {}).get(val)
        if new:
            i = lines[ln].find(val, col)
            lines[ln] = lines[ln][:i] + new + lines[ln][i + len(val):]
    return "\n".join(lines)


def edit_toml(text, moves):
    return re.sub(r'(?m)^(\s*model\s*=\s*")([^"]+)(")',
                  lambda m: m[1] + moves.get("codex", {}).get(m[2], m[2]) + m[3], text)


def edit_text(text, mapping):
    for old, new in mapping.items():
        text = re.sub(rf"(?<![\w.-]){re.escape(old)}(?![\w-]|\.\d)", new, text)
    return text


def configs():
    return [p for p in [f"{H}/.hermes/config.yaml"] + sorted(glob.glob(f"{H}/.hermes/profiles/*/config.yaml"))
            if os.path.exists(p)]


def rule_files():
    return sorted(glob.glob(f"{H}/.hermes/plugins/ops-core/rules/*.md") + glob.glob(f"{H}/agents/rules/*.md")
                  + glob.glob(f"{H}/.hermes/profiles/*/plugins/ops-core/rules/*.md"))


def in_use():
    used = {"codex": set(), "openai-api": set(), "claude": set()}
    for p in configs():
        t = open(p).read()
        for prov, _, _, val in yaml_values(t):
            if scope(prov) and GPT.fullmatch(val):
                used[scope(prov)].add(val)
        used["claude"] |= claude_names(yaml.safe_load(t))
    toml = f"{H}/.codex/config.toml"
    if os.path.exists(toml):
        used["codex"] |= {m[1] for m in re.finditer(r'(?m)^\s*model\s*=\s*"(gpt-[^"]+)"', open(toml).read())}
    st = f"{H}/.claude/settings.json"
    if os.path.exists(st):
        try:
            used["claude"] |= claude_names(json.load(open(st)))
        except ValueError:
            pass
    return used


def candidates(used, best):
    """{old: new} for used names whose family has a newer listed model."""
    out = {}
    for s in used:
        g = GPT.fullmatch(s)
        if g and g[2] in best and gver(best[g[2]]) > gver(s):
            out[s] = best[g[2]]
    return out


def openai_key():
    try:
        r = subprocess.run([f"{H}/.local/bin/hermes-sealed-env", "llm-api"], capture_output=True, text=True, timeout=30)
        return next((ln.split("=", 1)[1] for ln in r.stdout.splitlines() if ln.startswith("OPENAI_API_KEY=")), None)
    except OSError:
        return None


def openai_call(key, path, body=None):
    req = urllib.request.Request("https://api.openai.com/v1/" + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def codex_answers(slug):
    with tempfile.TemporaryDirectory() as d:
        try:
            r = subprocess.run(["codex", "exec", "-m", slug, "-s", "read-only", "--skip-git-repo-check",
                                "Reply with the single word ok and nothing else."],
                               cwd=d, capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return r.returncode == 0 and re.search(r"(?im)^\s*ok\W*$", r.stdout) is not None


def claude_alias(family):
    """Model id Claude Code's alias resolves to, or None when the call fails."""
    with tempfile.TemporaryDirectory() as d:
        try:
            r = subprocess.run(["claude", "-p", "--model", family, "--output-format", "json",
                                "Reply with the single word ok"], cwd=d, capture_output=True, text=True, timeout=180)
            out = json.loads(r.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
        if out.get("is_error"):
            return None
        ids = [k for k in out.get("modelUsage", {}) if CLAUDE.fullmatch(k) and family in k]
        return ids[0] if ids else None


def plan(moves):
    """{path: new_text} for every file the accepted moves change."""
    out = {}
    claude = moves.get("claude", {})
    for p in configs():
        t = open(p).read()
        n = edit_text(edit_yaml(t, moves), claude)
        if n != t:
            out[p] = n
    for p, f in ((f"{H}/.codex/config.toml", lambda t: edit_toml(t, moves)),
                 (f"{H}/.claude/settings.json", lambda t: edit_text(t, claude))):
        if os.path.exists(p):
            t = open(p).read()
            if f(t) != t:
                out[p] = f(t)
    for p in rule_files():  # rules talk about Codex runs and Claude models; API-only moves don't touch them
        t = open(p).read()
        n = edit_text(t, {**moves.get("codex", {}), **claude})
        if n != t:
            out[p] = n
    return out


def announce(moves, nfiles):
    """The assistant posts the switch in its home (assistant) channel through the gateway's bot."""
    try:
        chan = next((ln.split("=", 1)[1].strip() for ln in open(f"{H}/.hermes/.env")
                     if ln.startswith("DISCORD_HOME_CHANNEL=")), "")
    except OSError:
        return
    names = {"codex": "Codex", "openai-api": "OpenAI API fallback", "claude": "Claude"}
    lines = [f"- {names[sc]}: {o} → {n}" for sc, m in moves.items() for o, n in m.items()]
    msg = ("Models switched automatically to the newest of the same family:\n" + "\n".join(lines) +
           f"\nEach new model answered a test call first. {nfiles} config and rule files updated (backups kept); "
           "agents pick it up after the next idle gateway restart.")
    if chan:
        subprocess.run([f"{H}/.local/bin/discord-send", "--to", chan, "--no-wait", "--message", msg],
                       capture_output=True, timeout=120)


def selftest():
    best = newest_gpt(["gpt-6.1-sol", "gpt-6.2-sol", "gpt-6.2-astra", "gpt-6.1-terra", "gpt-reserve", "codex-auto-review"])
    assert best == {"sol": "gpt-6.2-sol", "astra": "gpt-6.2-astra", "terra": "gpt-6.1-terra"}, best
    assert candidates({"gpt-6.1-sol", "gpt-6.1-terra", "gpt-6.2-sol"}, best) == {"gpt-6.1-sol": "gpt-6.2-sol"}
    y = ("model:\n  base_url: x\n  default: gpt-6.1-sol\n  provider: openai-codex\n"
         "fallback_providers:\n- provider: claude-subscription-directsdk-experimental\n  model: claude-opus-5-5[1m]\n"
         "- provider: openai-api\n  model: gpt-6.1-sol\n  key_env: OPENAI_API_KEY\n"
         "deleg:\n  - name: deep\n    provider: openai-codex\n    model: gpt-6.1-sol  # c\n")
    m = {"codex": {"gpt-6.1-sol": "gpt-6.2-sol"}}
    t = edit_yaml(y, m)
    assert "default: gpt-6.2-sol" in t and "model: gpt-6.2-sol  # c" in t and "  model: gpt-6.1-sol\n  key_env" in t, t
    t2 = edit_yaml(y, {"openai-api": {"gpt-6.1-sol": "gpt-6.2-sol"}})
    assert "default: gpt-6.1-sol" in t2 and "  model: gpt-6.2-sol\n  key_env" in t2, t2
    c = edit_text(y, {"claude-opus-5-5": "claude-opus-5-6"})
    assert "model: claude-opus-5-6[1m]" in c, c
    assert edit_text("gpt-6.1-sol-mini gpt-6.1-sol.", {"gpt-6.1-sol": "X"}) == "gpt-6.1-sol-mini X."
    assert edit_toml('model = "gpt-6.1-sol"\nx = 1\n', m).startswith('model = "gpt-6.2-sol"')
    assert cver("claude-opus-5-5") < cver("claude-opus-5-10")
    print("ok")


def main():
    dry = "--dry-run" in sys.argv
    used = in_use()
    found, moves, kept = {}, {}, []
    try:  # Codex: free, from the CLI's cache
        found["codex"] = candidates(used["codex"], newest_gpt(
            m.get("slug", "") for m in json.load(open(f"{H}/.codex/models_cache.json")).get("models", [])
            if m.get("visibility", "list") == "list"))
    except (OSError, ValueError):
        pass
    key = openai_key() if used["openai-api"] else None
    if key:
        try:
            found["openai-api"] = candidates(used["openai-api"], newest_gpt(m["id"] for m in openai_call(key, "models")["data"]))
        except Exception as e:  # listing failed: leave the API fallback as it is
            kept.append(f"openai-api: model list failed ({type(e).__name__})")
    for sc, cand in found.items():
        for old, new in sorted(cand.items()):
            if dry:
                ok = True
            elif sc == "codex":
                ok = codex_answers(new)
            else:
                try:
                    ok = bool(openai_call(key, "responses", {"model": new, "input": "Reply ok", "max_output_tokens": 16}))
                except Exception:
                    ok = False
            if ok:
                moves.setdefault(sc, {})[old] = new
            else:
                kept.append(f"{sc}: keep {old}, {new} did not answer")
    for fam in sorted({CLAUDE.fullmatch(s)[1] for s in used["claude"]}):
        cur = max((s for s in used["claude"] if CLAUDE.fullmatch(s)[1] == fam), key=cver)
        if dry:
            print(f"claude {fam}: in use {sorted(s for s in used['claude'] if fam in s)} (alias not checked in a dry run)")
            continue
        new = claude_alias(fam)
        if not new:
            kept.append(f"claude: keep {fam}, the alias call failed (limit or login)")
            continue
        for s in used["claude"]:
            if CLAUDE.fullmatch(s)[1] == fam and cver(new) > cver(s):
                moves.setdefault("claude", {})[s] = new
    for k in kept:
        print(k)
    if dry:
        print("in use:", {k: sorted(v) for k, v in used.items()})
    if not moves:
        return
    files = plan(moves)
    summary = ", ".join(f"{sc} {o} -> {n}" for sc, m in moves.items() for o, n in m.items())
    print(f"{'would switch' if dry else 'switched'} {summary} in {len(files)} files")
    stamp = datetime.date.today().isoformat()
    for path, text in files.items():
        print("  " + path.replace(H, "~"))
        if dry:
            continue
        bdir = f"{H}/agents/backups"; os.makedirs(bdir, exist_ok=True)
        shutil.copy2(path, f"{bdir}/{path.replace(H + '/', '').replace('/', '_')}.bak-{stamp}-model-follow")
        with open(path, "w") as f:
            f.write(text)
    if dry or not files:
        return
    now = datetime.datetime.now().strftime("%F %T")
    os.makedirs(f"{H}/.local/state", exist_ok=True)
    open(f"{H}/.local/state/cli-update.log", "a").write(f"{now} models {summary} ({len(files)} files)\n")
    adm = f"{H}/agents/ADMIN-CHANGES.md"
    if os.path.exists(adm):
        open(adm, "a").write(f"\n- {now} model-follow: {summary} in Hermes, Codex and Claude Code configs and rules "
                             f"(backups ~/agents/backups/*.bak-{stamp}-model-follow).\n")
    if any("/rules/" in p for p in files):
        subprocess.run([f"{H}/.local/bin/hermes", "ops-rules", "apply"], capture_output=True, timeout=300)
    announce(moves, len(files))
    subprocess.run(["sudo", "-n", "systemd-run", "--unit", f"hermes-restart-idle-{int(datetime.datetime.now().timestamp())}",
                    "--collect", f"{H}/.local/bin/hermes-restart-idle", "--max-wait", "21600"], capture_output=True)


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
