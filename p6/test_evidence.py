import unittest
from evidence import kernel_anomalies


class Evidence(unittest.TestCase):
    def test_unhandled_windows_vector_is_not_clean_kernel_evidence(self):
        warning = '[ 22.716225] No irq handler for 0.225'
        self.assertEqual(kernel_anomalies('Installing driver\n'+warning), [warning])

    def test_normal_log_does_not_match_stall_substring(self):
        self.assertEqual(kernel_anomalies('Installing driver\nLWLAB: firmware-ready'), [])


if __name__ == '__main__':
    unittest.main()
