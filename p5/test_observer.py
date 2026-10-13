"""Meaningful paging failures: large pages, stale translations, and boundaries."""
import struct,unittest
from observer import Virtual,Unavailable,Changed
class RAM:
 def __init__(self):self.b=bytearray(1<<20);self.generation=1;self.reads=0;self.change=False
 def owns(self,a,n):return 0<=a<len(self.b) and n<=len(self.b)-a
 def read(self,a,n):
  if not self.owns(a,n):raise Unavailable('range')
  self.reads+=1
  if self.change and a==0x8000:self.put(0x4000,0x9003 if self.u64(0x4000)==0x8003 else 0x8003)
  return bytes(self.b[a:a+n])
 def u64(self,a):return struct.unpack('<Q',self.read(a,8))[0]
 def put(self,a,v):struct.pack_into('<Q',self.b,a,v)
class Paging(unittest.TestCase):
 def setUp(self):
  self.p=RAM();self.p.put(0x1000,0x2003);self.p.put(0x2000,0x3003);self.p.put(0x3000,0x4003);self.p.put(0x4000,0x8003);self.v=Virtual(self.p,0x1000)
 def test_4k(self):self.assertEqual(self.v.walk(0x123)[0],0x8123)
 def test_2m(self):self.p.put(0x3000,0x83);self.assertEqual(self.v.walk(0x123)[2],21)
 def test_1g(self):self.p.put(0x2000,0x83);self.assertEqual(self.v.walk(0x123)[2],30)
 def test_pat_large(self):self.p.put(0x3000,0x1083);self.assertEqual(self.v.walk(0x123)[0],0x123)
 def test_nonresident(self):
  self.p.put(0x4000,0x8000)
  with self.assertRaises(Unavailable):self.v.read(0,8)
 def test_noncanonical(self):
  with self.assertRaises(Unavailable):self.v.walk(1<<48)
 def test_misaligned_large(self):
  self.p.put(0x3000,0x2083)
  with self.assertRaises(Unavailable):self.v.walk(0)
 def test_boundary(self):
  self.p.put(0x4008,0xb003);self.p.b[0x8fff]=12;self.p.b[0xb000]=34
  self.assertEqual(self.v.read(4095,2),bytes([12,34]))
 def test_changed_mapping_retried(self):
  self.p.change=True;self.p.b[0x8000]=1;self.p.b[0x9000]=2
  self.assertEqual(self.v.read(0,1),b'\x02')
 def test_outside_partition(self):
  self.p.put(0x4000,0x200003)
  with self.assertRaises(Unavailable):self.v.read(0,1)
if __name__=='__main__':unittest.main()
