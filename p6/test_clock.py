import copy,unittest
from windows_clock import read_clock,UnstableClock,SHARED_USER_DATA
PROFILE={'types':{'_KUSER_SHARED_DATA':{'fields':{'SystemTime':20,'NtBuildNumber':608}},'_KSYSTEM_TIME':{'fields':{'LowPart':0,'High1Time':4,'High2Time':8}}}}
class Clock(unittest.TestCase):
 def test_read_and_build_rejection(self):
  class V:
   def u32(self,a):return {608:26100,20:123,24:10,28:10}[a-SHARED_USER_DATA]
  self.assertEqual(read_clock(V(),PROFILE,26100),(10<<32)|123)
  with self.assertRaises(UnstableClock):read_clock(V(),PROFILE,26101)
 def test_torn_high_word_is_rejected(self):
  class V:
   def u32(self,a):return {608:26100,20:123,24:11,28:10}[a-SHARED_USER_DATA]
  with self.assertRaises(UnstableClock):read_clock(V(),PROFILE,26100)
 def test_interrupt_time_uses_profile_and_rejects_other_fields(self):
  p=copy.deepcopy(PROFILE);p['types']['_KUSER_SHARED_DATA']['fields']['InterruptTime']=8
  class V:
   def u32(self,a):return {608:26100,8:456,12:1,16:1}[a-SHARED_USER_DATA]
  self.assertEqual(read_clock(V(),p,26100,'InterruptTime'),(1<<32)|456)
  with self.assertRaises(ValueError):read_clock(V(),p,26100,'BootId')
if __name__=='__main__':unittest.main()
