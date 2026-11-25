#!/bin/bash
# Test for camofox-password-mask-apply.py: a page with a filled password field must not show its value in /snapshot.
# Usage: camofox-password-mask-test.sh [camofox port, default 9377]. Exit 0 = masked, 1 = leaked or failed.
set -u
PORT=${1:-9377}
CF=http://127.0.0.1:$PORT
dir=$(mktemp -d)
cat > "$dir/index.html" <<'EOF'
<html><body><form><label for=u>Email</label><input id=u value="tester@example.invalid">
<label for=p>Password</label><input id=p type=password value="Zq9-maskTest'x\y">
<button>Sign in</button></form></body></html>
EOF
python3 -m http.server 8799 --bind 127.0.0.1 --directory "$dir" >/dev/null 2>&1 &
web=$!
trap 'kill $web 2>/dev/null; rm -rf "$dir"' EXIT
sleep 1
user=pwmask_test_$$
tab=$(curl -s -m 60 -X POST "$CF/tabs" -H 'content-type: application/json' \
  -d "{\"userId\":\"$user\",\"sessionKey\":\"pwmask\",\"url\":\"http://127.0.0.1:8799/index.html\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("tabId",""))')
[ -n "$tab" ] || { echo "FAIL: could not open tab"; exit 1; }
snap=$(curl -s -m 60 "$CF/tabs/$tab/snapshot?userId=$user")
curl -s -m 30 -X DELETE "$CF/sessions/$user" >/dev/null
if grep -q "maskTest" <<<"$snap"; then echo "FAIL: password value leaked in snapshot"; exit 1; fi
grep -q "tester@example.invalid" <<<"$snap" || { echo "FAIL: snapshot missing normal field (got: ${snap:0:300})"; exit 1; }
grep -q '\*\*\*\*\*\*\*\*' <<<"$snap" || echo "note: no mask marker (field value not shown at all)"
echo "OK: password masked, normal values kept"
