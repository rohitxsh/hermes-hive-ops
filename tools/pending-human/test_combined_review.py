"""Exact-pair inbox consolidation: pending-human retains each independent wait by default."""
from pathlib import Path
import json
import os
import runpy
import sqlite3
import tempfile
import unittest

TARGET = Path(os.environ.get('PH_TARGET', Path(__file__).with_name('pending-human')))
SOURCE = {'id': 'screen', 'status': 'scheduled', 'assignee': 'design',
          'reason': 'EXTERNAL_EVENT_WAIT: this screen verdict is collected on the combined review.'}
CANONICAL = {'id': 'feature', 'status': 'scheduled', 'assignee': 'pm',
             'reason': 'waiting on reviewer1 and reviewer2 for a decision'}
DISPLAY = 'waiting on reviewer1 and reviewer2 for combined review (requirements, screens and architecture): https://github.com/example/app/issues/422#issuecomment-1'


class CombinedReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'board.db'
        self.conf = Path(self.tmp.name) / 'combined-review.json'
        self.spec = dict(companion=SOURCE, canonical=CANONICAL, display_reason=DISPLAY)
        self.conf.write_text(json.dumps(self.spec))
        self.wait = runpy.run_path(str(TARGET), run_name='pending_human_test')['waiting_cards']
        self.wait.__globals__['COMBINED_REVIEW'] = self.conf

    def read(self, *records, newer=None):
        with sqlite3.connect(self.db) as c:
            c.executescript('create table tasks(id, status, assignee, title, block_kind); '
                            'create table task_events(id integer primary key, task_id, kind, created_at, payload)')
            for r in records:
                c.execute('insert into tasks values (?,?,?,?,?)', (r['id'], r['status'], r['assignee'], r['id'], None))
                c.execute('insert into task_events(task_id,kind,created_at,payload) values(?,?,?,?)',
                          (r['id'], r['status'], 100, json.dumps({'reason': r['reason']})))
            if newer:
                c.execute('insert into task_events(task_id,kind,created_at,payload) values(?,?,?,?)',
                          ('screen', 'scheduled', 100, json.dumps({'reason': newer})))
        c.close()
        before = self.db.read_bytes()
        found = {r['id']: r for r in self.wait(str(self.db), 3700)}
        self.assertEqual(self.db.read_bytes(), before)
        return found

    def test_exact_pair_consolidates_only_companion(self):
        other = dict(SOURCE, id='other')
        found = self.read(SOURCE, CANONICAL, other)
        self.assertEqual(set(found), {'feature', 'other'})
        self.assertEqual(found['feature']['reason'], DISPLAY + '\n' + CANONICAL['reason'])
        self.assertEqual(found['feature']['waiting_hours'], 1.0)
        self.assertEqual(found['other']['reason'], SOURCE['reason'])

    def test_newer_same_second_screen_wait_stays_visible(self):
        found = self.read(SOURCE, CANONICAL, newer='waiting on reviewer1 for new independent screen review')
        self.assertEqual(set(found), {'screen', 'feature'})
        self.assertIn('new independent screen review', found['screen']['reason'])

    def test_missing_canonical_keeps_screen_visible(self):
        self.assertEqual(set(self.read(SOURCE)), {'screen'})

    def test_changed_canonical_reason_keeps_screen_visible(self):
        self.assertEqual(set(self.read(SOURCE, dict(CANONICAL, reason='waiting for updated material'))), {'screen', 'feature'})

    def test_changed_assignee_keeps_screen_visible(self):
        self.assertEqual(set(self.read(dict(SOURCE, assignee='qa'), CANONICAL)), {'screen', 'feature'})

    def test_malformed_config_keeps_both_visible(self):
        self.conf.write_text('{bad')
        self.assertEqual(set(self.read(SOURCE, CANONICAL)), {'screen', 'feature'})

    def test_disabled_config_keeps_both_visible(self):
        self.conf.unlink()
        self.assertEqual(set(self.read(SOURCE, CANONICAL)), {'screen', 'feature'})


if __name__ == '__main__':
    unittest.main()
