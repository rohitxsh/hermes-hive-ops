#!/usr/bin/env python3
"""Offline model-scope regressions; no model/provider calls or board writes."""
import contextlib
import copy
import io
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent  # tools/quota in the kit, ~/agents/src/quota on a VM
sys.path.insert(0, str(ROOT))
import quota_lib as q
STATUS = os.environ.get('QUOTA_STATUS_TARGET', str(ROOT/'quota-status'))
NS = runpy.run_path(STATUS, run_name='quota_status_test')
ATT = runpy.run_path(str(ROOT.parent / 'attention' / 'attention'), run_name='quota_attention_test')
RESET = '2026-11-18T09:59:59.871845+00:00'
WINDOWS = q.claude_windows_from_limits({
    'five_hour': {'utilization': 0, 'resets_at': RESET},
    'seven_day': {'utilization': 50, 'resets_at': RESET},
    'model_scoped': [{'display_name': 'Fable', 'utilization': 100, 'resets_at': RESET}]})

class ModelScopes(unittest.TestCase):
    def cli(self, args, windows=WINDOWS):
        calls=[]
        def usage(provider, **kw):
            calls.append(provider)
            return copy.deepcopy(windows if q.is_claude(provider) else [q._window('weekly', 1, RESET)])
        cfg={'model': {'provider':'openai-codex','default':'gpt-6.1-sol'},
             'fallback_providers':[{'provider':'claude-subscription-directsdk-experimental','model':'claude-opus-5-5'}]}
        out=io.StringIO(); err=io.StringIO(); code=0
        with patch.object(q,'load_config',return_value=cfg), patch.object(q,'usage',side_effect=usage), \
             patch.object(q,'recent_failures',return_value={}), patch.object(q,'caps',return_value=False), \
             patch.object(q,'auto_mode',return_value=False), patch.object(q,'paid_ok',return_value=False), \
             patch.object(sys,'argv',['quota-status',*args]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try: NS['main']()
            except SystemExit as exc: code=exc.code
        return code,out.getvalue(),err.getvalue(),calls

    def test_mythos_alias_applies_fable(self):
        self.assertEqual(3,len(q.scope_claude(WINDOWS,['claude-mythos-5-2'])))
    def test_fable_name_still_applies(self):
        self.assertEqual(3,len(q.scope_claude(WINDOWS,['claude-fable-5-1[1m]'])))
    def test_opus_and_mixed_fallback_not_globally_blocked(self):
        for models in ([],['claude-opus-5-5'],['claude-mythos-5-2','claude-opus-5-5']):
            self.assertEqual(2,len(q.scope_claude(WINDOWS,models)))
    def test_overview_exposes_scoped_window(self):
        code,out,err,calls=self.cli(['--fresh'])
        self.assertEqual(0,code); self.assertIn('Fable weekly 100% used',out)
        self.assertIn('Mythos',out); self.assertEqual(1,calls.count('claude-subscription-directsdk-experimental'))
    def test_mythos_gate_blocks_despite_available_opus(self):
        code,out,_,_=self.cli(['--gate','--claude-code','--model','claude-mythos-5-2'])
        self.assertEqual(1,code); self.assertIn('Fable weekly 100% used',out)
    def test_opus_gate_and_legacy_gate_remain_available(self):
        for args in (['--gate','--claude-code'],['--gate','--claude-code','--model','claude-opus-5-5']):
            code,out,_,_=self.cli(args); self.assertEqual(0,code); self.assertEqual('ok\n',out)
    def test_model_cannot_change_ordinary_provider_gate(self):
        code,_,_,_=self.cli(['--gate','--model','claude-mythos-5-2']); self.assertEqual(2,code)
    def test_nonclaude_model_rejected(self):
        code,_,_,_=self.cli(['--gate','--claude-code','--model','gpt-6.1-sol']); self.assertEqual(2,code)
    def test_attention_already_blocks_mythos_fable_and_weekly(self):
        for reason in ('Waiting for Mythos quota reset','Waiting for Fable limit reset',
                       'Waiting for Claude Mythos quota and Codex weekly reset'):
            self.assertIsNone(ATT['quota_back'](reason,lambda p: WINDOWS,(95,95)))
        self.assertIsNotNone(ATT['quota_back']('Waiting for Opus quota reset',lambda p: WINDOWS,(95,95)))
        weekly=[q._window('5-hour',0,RESET),q._window('weekly',97,RESET)]
        self.assertIsNone(ATT['quota_back']('Waiting for Claude Mythos quota reset',lambda p: weekly,(95,95)))
    def test_attention_unknown_and_person_wait_fail_closed(self):
        self.assertIsNone(ATT['quota_back']('Waiting for Mythos quota reset',lambda p:None,(95,95)))
        self.assertIsNone(ATT['quota_back']('waiting on Alex for Mythos quota decision',lambda p:WINDOWS,(95,95)))
    def test_original_shared_reading_is_not_modified(self):
        baseline=copy.deepcopy(WINDOWS); q.scope_claude(WINDOWS,['claude-mythos-5-2'])
        self.assertEqual(baseline,WINDOWS)

if __name__=='__main__': unittest.main()
