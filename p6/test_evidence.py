import unittest
from evidence import kernel_anomalies,hal_errors


class Evidence(unittest.TestCase):
    def test_unhandled_windows_vector_is_not_clean_kernel_evidence(self):
        warning = '[ 22.716225] No irq handler for 0.225'
        self.assertEqual(kernel_anomalies('Installing driver\n'+warning), [warning])

    def test_normal_log_does_not_match_stall_substring(self):
        self.assertEqual(kernel_anomalies('Installing driver\nLWLAB: firmware-ready'), [])

    def test_hal_boot_trace_cannot_replace_live_readback(self):
        serial='HAL probe matches=1 image=280200000\nHAL NoShorthand enforced=1 version=26100.1742'
        self.assertEqual(hal_errors(serial,[{'hal_no_shorthand':1}]),[])
        for samples in ([],[{}],[{'hal_no_shorthand':1},{'hal_no_shorthand':0}]):
            self.assertIn('hal_no_shorthand_not_retained',hal_errors(serial,samples))

    def test_probe_and_ambiguous_images_are_not_enforced(self):
        for serial in ('HAL probe matches=1 image=280200000 mode=1',
                       'HAL probe matches=2 image=280200000\nHAL NoShorthand enforced=1 version=26100.1742'):
            self.assertIn('hal_boot_adaptation_missing',hal_errors(serial,[{'hal_no_shorthand':1}]))


if __name__ == '__main__':
    unittest.main()
