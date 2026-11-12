import os, pathlib, subprocess, tempfile, unittest
TARGET = os.environ.get('HELPER', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local-supabase'))

class HelperTest(unittest.TestCase):
    def test_start_establishes_loopback_before_cli(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as td:
            root = pathlib.Path(td)
            bins = root / '.local/bin'; bins.mkdir(parents=True)
            repo = root / 'repo'; (repo / 'supabase').mkdir(parents=True)
            (repo / 'supabase/config.toml').write_text('project_id = "safe-unit"\n')
            (bins / 'docker').write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$HOME/docker-calls"
case "$1 $2" in
  'network create') echo synthetic-network ;;
  'network inspect') printf '%s|safe-unit\\n' "$HOME/repo" ;;
  'ps -q'*) echo fake-container ;;
  'inspect --format'*) printf '{"8000/tcp":[{"HostIp":"%s","HostPort":"54321"}]}\\n' "${FAKE_IP:-127.0.0.1}" ;;
  'ps '*) : ;;
esac
''')
            (bins / 'supabase').write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$HOME/cli-calls"
if [[ "$1" = start ]]; then
  [[ "$*" = *--network-id* ]] || { echo 'missing safe network' >&2; exit 23; }
  grep -q 'host_binding_ipv4=127.0.0.1' "$HOME/docker-calls" || exit 24
fi
''')
            for p in bins.iterdir(): p.chmod(0o700)
            result = subprocess.run(['bash', TARGET, 'start', str(repo)], env={**os.environ, 'HOME': td, 'LOCAL_SUPABASE_MIN_MB': '0'}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--network-id', (root / 'cli-calls').read_text())
            self.assertIn('host_binding_ipv4=127.0.0.1', (root / 'docker-calls').read_text())
            for ip in ('0.0.0.0', '::'):
                result = subprocess.run(['bash', TARGET, 'start', str(repo)], env={**os.environ, 'HOME': td, 'LOCAL_SUPABASE_MIN_MB': '0', 'FAKE_IP': ip}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 6, result.stderr)
                self.assertIn('unsafe non-loopback', result.stderr)
                self.assertIn('stop --workdir', (root / 'cli-calls').read_text())
                self.assertIn('network rm', (root / 'docker-calls').read_text())
            result = subprocess.run(['bash', TARGET, 'start', str(repo)], env={**os.environ, 'HOME': td, 'LOCAL_SUPABASE_MIN_MB': '999999999'}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 4, result.stderr)

    def test_mailbox_refuses_nonloopback_and_credentials(self):
        for url in ('http://192.0.2.1:54324', 'https://127.0.0.1', 'http://user:password@127.0.0.1:54324'):
            result = subprocess.run(['bash', TARGET, 'code', 'synthetic@example.invalid'], capture_output=True, text=True, env={**os.environ, 'LOCAL_SUPABASE_MAILPIT': url})
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')

    def test_code_does_not_mistake_link_hash_for_otp(self):
        import http.server, threading
        fixture = {'text': 'https://localhost/verify?token=abcdef123456abcdef', 'redirect': False, 'hits': []}
        class Mailbox(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                import json
                fixture['hits'].append(self.path)
                if fixture['redirect']:
                    self.send_response(302); self.send_header('Location', '/forbidden'); self.end_headers(); return
                body = json.dumps({'messages': [{'ID': 'one'}]} if 'search?' in self.path else {'Text': fixture['text']}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(body)
            def log_message(self, *args): pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Mailbox)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            result = subprocess.run(['bash', TARGET, 'code', 'synthetic@example.invalid'], capture_output=True, text=True, env={**os.environ, 'LOCAL_SUPABASE_MAILPIT': f'http://127.0.0.1:{server.server_port}'})
            self.assertNotEqual(result.returncode, 0, 'link hash must not be reported as an OTP')
            self.assertEqual(result.stdout, '')
            fixture['text'] = 'Your code is 654321'
            env = {**os.environ, 'LOCAL_SUPABASE_MAILPIT': f'http://127.0.0.1:{server.server_port}', 'http_proxy': 'http://127.0.0.1:1', 'HTTP_PROXY': 'http://127.0.0.1:1', 'no_proxy': '', 'NO_PROXY': ''}
            result = subprocess.run(['bash', TARGET, 'code', 'synthetic@example.invalid'], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), '654321')
            fixture['redirect'] = True
            fixture['hits'].clear()
            result = subprocess.run(['bash', TARGET, 'code', 'synthetic@example.invalid'], capture_output=True, text=True, env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
            self.assertNotIn('/forbidden', fixture['hits'])
        finally:
            server.shutdown(); server.server_close(); thread.join()

if __name__ == '__main__': unittest.main()
