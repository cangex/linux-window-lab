import importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('semantics',Path(__file__).with_name('verify-semantics.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Semantics(unittest.TestCase):
 def fixtures(self):
  truth=[dict(nonce='boot',time=i*10000000,pid=10,created=20,child=30,module=40,events=1,helper=False,errors=0) for i in range(5)]
  observations=[dict(event='bootstrap',generation=7,kernel=90,address_helper_used=False)]
  for i in (1,2,3):observations.append(dict(event='sample',generation=7,windows_begin=i*10000000+2000000,windows_end=i*10000000+2100000,monotonic_begin=i*1000000000+200000000,monotonic_end=i*1000000000+210000000,target=dict(pid=10,created=20,generation=7),children=[dict(pid=30)],module=40,kernel_module=dict(base=90)))
  return truth,observations
 def test_stable_match(self):
  t,o=self.fixtures();r=m.verify(t,o,'boot',3);self.assertTrue(r['passed']);self.assertEqual(r['stable_matched'],3)
 def test_wrong_object_fails(self):
  t,o=self.fixtures();o[2]['target']['created']=99;r=m.verify(t,o,'boot',1);self.assertFalse(r['passed']);self.assertEqual(r['mismatches'],[1])
 def test_changes_and_unavailable_count_against_coverage(self):
  t,o=self.fixtures();t[2]['events']=2;o.append(dict(event='unavailable',generation=7));r=m.verify(t,o,'boot',1);self.assertEqual(r['excluded'],2);self.assertEqual(r['unavailable'],1);self.assertEqual(r['coverage'],.25);self.assertFalse(r['passed'])
 def test_reject_unaligned_or_stale(self):
  for change in ('clock','generation','missing'):
   t,o=self.fixtures()
   if change=='clock':o[2]['windows_end']+=5000000
   if change=='generation':o[2]['generation']=8
   if change=='missing':del o[2]['windows_begin']
   with self.assertRaises(ValueError):m.verify(t,o,'boot',1)
if __name__=='__main__':unittest.main()
