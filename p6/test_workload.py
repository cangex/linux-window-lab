import copy,importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('workload',Path(__file__).with_name('verify-workload.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Workload(unittest.TestCase):
 def records(self):
  return [dict(schema=1,helper=False,nonce='boot1',pid=32,created=100,time=100000+i*10000000,seconds=i,io=i,errors=0,child=42 if i%4<2 else 0,module=1024 if i%4<2 else 0,cpus=[dict(cpu=j,loops=i*(j+1),errors=0) for j in range(4)]) for i in range(10)]
 def test_progress_and_lifecycles(self):
  r=m.verify(self.records(),4,9);self.assertTrue(r['workload_passed']);self.assertFalse(r['external_semantics_verified']);self.assertEqual(r['cpu_loops'],[9,18,27,36]);self.assertEqual(r['child_starts'],2);self.assertEqual(r['dll_unloads'],2)
 def test_reject_corruption_stall_missing_cpu_and_restart(self):
  for fault in ('error','worker','stall','clock','identity','helper','regression'):
   with self.subTest(fault=fault):
    r=self.records()
    if fault=='error':r[4]['errors']=1
    if fault=='worker':r[4]['cpus'].pop()
    if fault=='stall':
     for x in r:x['cpus'][0]['loops']=0
    if fault=='clock':r[4]['time']=r[3]['time']
    if fault=='identity':r[4]['created']=99
    if fault=='helper':r[4]['helper']=True
    if fault=='regression':r[4]['io']=0
    with self.assertRaises(ValueError):m.verify(r,4,9)
 def test_reject_short_and_unobserved_gap(self):
  with self.assertRaises(ValueError):m.verify(self.records(),4,10)
  with self.assertRaises(ValueError):m.verify([self.records()[0],self.records()[-1]],4,9,max_gap=3)
if __name__=='__main__':unittest.main()
