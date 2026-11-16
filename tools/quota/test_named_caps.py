"""Regressions for explicit provider caps with a healthy primary."""
import unittest
from unittest.mock import patch
import quota_lib as q


class NamedCaps(unittest.TestCase):
    def setUp(self):
        for name, value in [('NO_CAPS', False), ('AUTO_CAP', 70.0), ('WEEKLY_CAP', 80.0), ('WRAP_MARGIN', 10.0)]:
            p = patch.object(q, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.chain = ['openai-codex', 'claude-subscription-directsdk-experimental', 'anthropic']

    def usage(self, percent):
        return lambda p: [{'label': 'weekly', 'used': percent if q.is_claude(p) else 20, 'resets_at': None}]

    def test_explicit_claude_cap_stops_even_with_healthy_codex(self):
        for percent in (80, 81, 100):
            with self.subTest(percent=percent):
                allowed, reason = q.run_allowed(self.chain, True, self.usage(percent), ('claude',))
                self.assertFalse(allowed)
                self.assertIn('weekly', reason)


    def test_named_claude_warns_before_cap_with_healthy_codex(self):
        self.assertIn('Claude', q.wrap_up(self.chain, True, self.usage(75), ('claude',)))

    def test_non_named_caps_keep_existing_primary_policy(self):
        self.assertTrue(q.run_allowed(self.chain, True, self.usage(81))[0])
        self.assertTrue(q.run_allowed(self.chain, False, self.usage(81), ('claude',))[0])
        self.assertTrue(q.run_allowed(self.chain, True, self.usage(60), ('claude',))[0])
        self.assertFalse(q.wrap_up(self.chain, True, self.usage(60), ('claude',)))

    def test_five_hour_cap_also_applies_before_fallback(self):
        usage = lambda p: [{'label': '5-hour', 'used': 71 if q.is_claude(p) else 20, 'resets_at': None}]
        self.assertFalse(q.run_allowed(self.chain, True, usage, ('claude',))[0])

    def test_disabled_caps_remain_disabled(self):
        with patch.object(q, 'NO_CAPS', True):
            self.assertTrue(q.run_allowed(self.chain, True, self.usage(81), ('claude',))[0])


if __name__ == '__main__':
    unittest.main()
