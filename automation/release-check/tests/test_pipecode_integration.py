"""Tests for the two PIPECODE hooks in release_check.py: verdict honesty in check2_row, training_signal column."""
import json
import os
import sys
import tempfile
import unittest

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(H))
import release_check as rc  # noqa: E402

V = {'7': dict(task_id='7', verdict='PASS', reason='no material item', n_unverified='0', n_unclear='0')}


def fx(sev, counted='0', verifier='CONFIRMED'):
    return dict(task_id='7', review_id='r1', idx='1', criteria='c01', severity_stated=sev, counted_in_verdict=counted,
                verifier=verifier, type='X', weight_confirmed='', weight_stated='')


class VerdictHonesty(unittest.TestCase):
    def test_pass_with_clean_fixlist_stays_no(self):
        self.assertEqual(rc.check2_row('7', V, [fx('minor')], 0, True, True)[0], 'no')

    def test_pass_with_unrefuted_major_becomes_hold(self):
        r = rc.check2_row('7', V, [fx('major')], 0, True, True)
        self.assertEqual(r[0], 'yes'); self.assertIn('HOLD', r[1])

    def test_blocking_counts_as_major(self):
        self.assertEqual(rc.check2_row('7', V, [fx('blocking')], 0, True, True)[0], 'yes')

    def test_refuted_major_does_not_block(self):
        self.assertEqual(rc.check2_row('7', V, [fx('major', verifier='REFUTED')], 0, True, True)[0], 'no')


def write_run(d, rid, model, reward, checks):
    det = {'deliverables_01': {'criteria': [{'name': n, 'value': v, 'weight': w} for n, v, w in checks]}}
    json.dump(det, open(os.path.join(d, '%s.reward-details.json' % rid), 'w'))


class TrainingSignal(unittest.TestCase):
    def test_warning_and_ok_and_overall_untouched(self):
        d = tempfile.mkdtemp()
        runs, details = {}, {}
        for i in range(2):
            rid = str(10 + i)
            write_run(d, rid, 'm', 1.0, [('a', 1.0, 0.5), ('b', 1.0, 0.5)])
            runs[rid] = dict(agent='CODEX', status='PASSED', reward='1.0', task='7', model='gpt-x')
            details[rid] = os.path.join(d, '%s.reward-details.json' % rid)
        line = rc.training_signal('7', runs, details)
        self.assertTrue(line.startswith('HEADROOM WARNING: '))
        self.assertEqual(rc.overall('no', 'no', 'SEND'), 'RELEASE')  # warning never changes overall
        row = dict(check1_c_fail='no', check2_v11='no', check3_gate='SEND', training_signal=line, check1_reason='',
                   check2_reason='', check3_missing_inputs='', check1_rules='', check2_rules='', check3_rules='')
        self.assertIn('report only', rc.message(row))

    def test_no_runs(self):
        self.assertTrue(rc.training_signal('9', {}, {}).startswith('HEADROOM WARNING'))


if __name__ == '__main__':
    unittest.main()
