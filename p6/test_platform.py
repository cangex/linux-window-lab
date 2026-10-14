"""Validate generated ACPI/HOB bytes independently of the firmware build."""
import importlib.util,json,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
class Platform(unittest.TestCase):
 def check_platform(self,count):
  with tempfile.TemporaryDirectory() as temp:
   directory=Path(temp)/'stage';disk=Path(temp)/'placeholder.img';disk.touch()
   subprocess.run([sys.executable,str(ROOT/'stage.py'),str(directory),'--cpus',str(count),'--disk',str(disk)],check=True,capture_output=True)
   spec=importlib.util.spec_from_file_location('pack',directory/'pack.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   data,addresses=m.acpi(m.acpi_table(b'DSDT',b'',2));start=m.A('acpi')
   def table(name):
    at=int(addresses[name],16)-start;n=struct.unpack_from('<I',data,at+4)[0];raw=data[at:at+n]
    self.assertEqual(sum(raw)%256,0);return raw
   madt=table('APIC');ids=[];pos=44
   while pos<len(madt):
    kind,size=madt[pos:pos+2]
    if kind==0:
     self.assertEqual(size,8);ids.append(madt[pos+3]);self.assertEqual(struct.unpack_from('<I',madt,pos+4)[0],1)
    pos+=size
   self.assertEqual(ids,list(range(4,4+count)))
   srat=table('SRAT');ids=[];pos=48
   while pos<len(srat):
    kind,size=srat[pos:pos+2]
    if kind==0:ids.append(srat[pos+3])
    pos+=size
   self.assertEqual(ids,list(range(4,4+count)))
   hobs=m.hobs(4096,m.A('core'),4096);pos=0;reserved=[]
   while pos<len(hobs):
    kind,size=struct.unpack_from('<HH',hobs,pos)
    if kind==2:reserved.append(struct.unpack_from('<QQI',hobs,pos+24))
    if kind==0xffff:break
    pos+=size
   self.assertIn((0x6f000,4096,0),reserved)
   cfg=json.loads((directory/'partition.json').read_text())
   self.assertFalse(set(cfg['windows_cpus'])&set(cfg['linux_cpus']))
 def test_one_cpu(self):self.check_platform(1)
 def test_two_cpus(self):self.check_platform(2)
 def test_four_cpus(self):self.check_platform(4)
 def test_invalid_count_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   result=subprocess.run([sys.executable,str(ROOT/'stage.py'),str(Path(temp)/'stage'),'--cpus','8','--disk','unused'],capture_output=True)
   self.assertNotEqual(result.returncode,0)
if __name__=='__main__':unittest.main()
