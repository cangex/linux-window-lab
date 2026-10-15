import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('attempt', Path(__file__).with_name('verify-attempt.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Attempt(unittest.TestCase):
    def test_selects_observed_identity_not_last_boot(self):
        truth = [dict(pid=10, created=20, nonce='observed'), dict(pid=10, created=30, nonce='later')]
        observations = [dict(event='sample', target=dict(pid=10, created=20))]
        rows, nonce = m.select_truth(truth, observations)
        self.assertEqual(nonce, 'observed')
        self.assertEqual(len(rows), 1)

    def test_missing_reused_and_ambiguous_identities_rejected(self):
        observed = dict(event='sample', target=dict(pid=10, created=20))
        with self.assertRaises(ValueError):
            m.select_truth([dict(pid=10, created=30, nonce='reused')], [observed])
        with self.assertRaises(ValueError):
            m.select_truth([dict(pid=10, created=20, nonce=n) for n in ('a', 'b')], [observed])
        with self.assertRaises(ValueError):
            m.select_truth([], [observed, dict(event='sample', target=dict(pid=11, created=21))])


if __name__ == '__main__':
    unittest.main()
