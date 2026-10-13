"""Ensure post-stop validation rejects wrong data and active helper channels."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('offline',Path(__file__).with_name('verify-offline.py'))
offline=importlib.util.module_from_spec(spec);spec.loader.exec_module(offline)

class OfflineVerification(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);(self.root/'semantics').mkdir()
  self.truth=[];self.samples=[]
  for sec in range(401):
   child=(0,10,11)[sec//60%3];module=4096 if sec//20%2 else 0
   self.truth.append(dict(nonce='000000000000002a',time=(11644473600+sec)*10_000_000,
    seconds=sec,pid=99,created=7,kernel='ffff0000',child=child,module=f'{module:x}',
    io=sec+1,errors=0,helper=False))
   if sec%10==5:
    processes=[dict(name='lwtruth.exe',pid=99,created=7)]
    if child:processes.append(dict(name='lwchild.exe',pid=child))
    self.samples.append(dict(event='sample',time=sec+.5,processes=processes,
     target_modules=[dict(name='lwlifecycle.dll',base=module)] if module else [],
     kernel_modules=[dict(name='ntoskrnl.exe',base=0xffff0000)]))
  self.save()
 def save(self):
  def write(name,rows):(self.root/name).write_text('\n'.join(map(json.dumps,rows)))
  write('offline-truth.jsonl',self.truth)
  write('semantics/independent.jsonl',self.samples)
  write('semantics/comparison.jsonl',[dict(matches=True,truth=dict(nonce=42))])
 def test_stable_lifecycle(self):self.assertEqual(offline.verify(self.root)['stable_matched'],40)
 def test_wrong_module_rejected(self):
  self.samples[0]['target_modules']=[dict(name='lwlifecycle.dll',base=42)];self.save()
  with self.assertRaises(AssertionError):offline.verify(self.root)
 def test_storage_error_rejected(self):
  self.truth[-1]['errors']=1;self.save()
  with self.assertRaises(AssertionError):offline.verify(self.root)
 def test_live_helper_rejected(self):
  for row in self.truth:row['helper']=True
  self.save()
  with self.assertRaises(AssertionError):offline.verify(self.root)
 def test_wrong_boot_rejected(self):
  for row in self.truth:row['nonce']='000000000000002b'
  self.save()
  with self.assertRaises(AssertionError):offline.verify(self.root)
