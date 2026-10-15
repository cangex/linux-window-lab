import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('recovery_verify', Path(__file__).with_name('verify-recovery.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RecoveryEvidence(unittest.TestCase):
    def fixture(self, out):
        (out / 'linux').mkdir()
        def write(name, value):
            (out / name).write_text(json.dumps(value))
        write('before.json', dict(boot_id='linux-same', cycles=1))
        write('collection-result.json', dict(recovery_collection_passed=True))
        write('linux/result.json', {'pass': True, 'boot_id': 'linux-same'})
        old = dict(target=dict(pid=10, created=100), windows_boot_id=5)
        first = dict(target=dict(pid=20, created=200), windows_boot_id=6,
                     interrupt_time_100ns=100, cpus=[dict(Number=i, InitialApicId=4+i, CycleTime=100) for i in range(4)])
        last = copy.deepcopy(first)
        last['interrupt_time_100ns'] = 200
        for cpu in last['cpus']:
            cpu['CycleTime'] = 200
        events = [dict(event='before', linux_boot_id='linux-same', running=old, state=dict(generation='1')),
                  dict(event='stop', state=dict(state='stopped', started='0')),
                  dict(event='quiescence', bus_master_disabled=True, pci_command=2,
                       kernel_log=[f'LWLAB P6: four parked CPUs and NVMe reset; nonce={(1<<63)+1} generation=1']),
                  dict(event='result', linux_boot_id='linux-same', partition_bootstrap_passed=True,
                       old_info_and_read_rejected=True, old_generation=1, new_generation=2,
                       running_before=first, running_after=last)]
        truth = [dict(nonce=str(pid), pid=pid, created=created, seconds=t, time=t*10000000,
                      schema=1, helper=False, errors=0, io=t, child=0, module=0,
                      cpus=[dict(cpu=i, loops=t, errors=0) for i in range(4)])
                 for pid, created in ((10, 100), (20, 200)) for t in (0, 10)]
        (out / 'dmesg.txt').write_text('normal kernel log\n')
        return events, truth

    def check(self, out, events, truth):
        (out / 'cycle-01.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events))
        (out / 'p6-truth.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in truth))
        return m.verify(out)

    def test_accepts_complete_independent_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            events, truth = self.fixture(out)
            result = self.check(out, events, truth)
            self.assertTrue(result['independent_restart_passed'])
            self.assertFalse(result['formal_p6_acceptance'])

    def test_rejects_unchanged_boot_dma_or_missing_truth(self):
        for failure in ('boot', 'dma', 'truth', 'linux'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                events, truth = self.fixture(out)
                if failure == 'boot':
                    events[0]['running']['windows_boot_id'] = 6
                elif failure == 'dma':
                    events[2]['pci_command'] |= 4
                elif failure == 'truth':
                    truth = truth[:2]
                else:
                    events[-1]['linux_boot_id'] = 'rebooted-linux'
                with self.assertRaises(AssertionError):
                    self.check(out, events, truth)


if __name__ == '__main__':
    unittest.main()
