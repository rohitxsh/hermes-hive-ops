#!/usr/bin/python3
"""Local Hermes patch (2026-11-02): Markdown attachments go out as PDFs. Every outbound attachment (chat replies,
send_message, cron and Kanban deliveries) passes gateway/platforms/base.py::_validated_delivery_path. With this patch a
validated .md/.markdown file is rendered with md-pdf (~/.local/bin/md-pdf) into ~/.cache/md-pdf/out/ and the PDF is
delivered instead, so people get one readable file per document. If md-pdf is missing, fails or takes over 45 s, the
.md goes out unchanged: nothing is dropped. Idempotent; `--check` only reports; `--test` runs the self-test with
Hermes's venv python. Re-run after `hermes update` if the self-check says it's missing, then restart the gateway."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "gateway/platforms/base.py"
TAG = ".bak-2026-11-02-mdaspdf"
MARK = "local patch (2026-11-02): md delivered as pdf"

A = ('''        if dropped is not None:
            dropped.append({"path": raw, "reason": reason})
    return safe_path
''')
B = ('''        if dropped is not None:
            dropped.append({"path": raw, "reason": reason})
    return _md_as_pdf(safe_path)  # ''' + MARK + '''
''')
H = f'''

def _md_as_pdf(path):
    """{MARK}: a Markdown attachment goes out as its formatted PDF so people get one readable file; on any
    failure the .md goes out unchanged."""
    if not path or not str(path).lower().endswith((".md", ".markdown")):
        return path
    tool = os.path.expanduser("~/.local/bin/md-pdf")
    if not os.path.isfile(tool):
        return path
    try:
        import hashlib
        st = os.stat(path)
        key = hashlib.sha256(f"{{path}}:{{st.st_mtime_ns}}:{{st.st_size}}".encode()).hexdigest()[:16]
        out_dir = os.path.expanduser(f"~/.cache/md-pdf/out/{{key}}")
        out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
        if not os.path.isfile(out):
            os.makedirs(out_dir, exist_ok=True)
            subprocess.run([tool, path, "-o", out], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, timeout=45)
        if os.path.isfile(out):
            return validate_media_delivery_path(out) or path
    except Exception as exc:
        logger.warning("md-as-pdf: sending the Markdown file as is (%s): %s", type(exc).__name__, _log_safe_path(str(path)))
    return path
'''


def selftest():
    import os, tempfile
    sys.path.insert(0, str(ROOT))
    from gateway.platforms import base as b
    d = tempfile.mkdtemp(dir=os.path.expanduser("~"))
    try:
        md = os.path.join(d, "note.md"); open(md, "w").write("# Title\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
        txt = os.path.join(d, "x.txt"); open(txt, "w").write("x")
        assert b._md_as_pdf(txt) == txt and b._md_as_pdf(None) is None
        pdf = b._md_as_pdf(md)
        assert pdf.endswith(".pdf") and open(pdf, "rb").read(5) == b"%PDF-", pdf
        assert b._md_as_pdf(md) == pdf  # cached
        assert b._validated_delivery_path(md, "", "test").endswith(".pdf")
        assert not os.path.exists(os.path.join(d, "note.pdf"))  # nothing written next to the source
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("selftest ok 6 cases")


s = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    ok = MARK in s
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in s:
    assert s.count(A) == 1, "_validated_delivery_path anchor not found once; upstream changed, patch by hand"
    s = s.replace(A, B).rstrip("\n") + "\n" + H
    compile(s, str(F), "exec")
    if not Path(str(F) + TAG).exists():
        shutil.copy2(F, str(F) + TAG)
    F.write_text(s, encoding="utf-8")
    print("patched", F)
print("ok")
