import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('gate',Path(__file__).with_name('resource-gate.py'));g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class Gate(unittest.TestCase):
 def test_stability_requires_continuous_window(self):
  rows=[dict(time=t,reasons=[]) for t in range(0,601,60)]
  self.assertTrue(g.stable(rows,600))
  self.assertFalse(g.stable(rows[1:],600))
  self.assertFalse(g.stable(rows[:3]+rows[5:],600))
  self.assertFalse(g.stable(rows,800))
  rows[4]['reasons']=['pressure'];self.assertFalse(g.stable(rows,600))
 def test_failure_outside_window_does_not_extend_it(self):
  rows=[dict(time=-60,reasons=['pressure'])]+[dict(time=t,reasons=[]) for t in range(0,601,60)]
  self.assertTrue(g.stable(rows,600))
  rows[1]['reasons']=['pressure'];self.assertFalse(g.stable(rows,600))
 def test_node_pressure_blocks_even_with_global_headroom(self):
  row=dict(available_gib=300,free_gib=200,disk_free_gib=100,psi_some_avg10=0,node_free_gib={'node0':3,'node1':20})
  self.assertEqual(g.assess(row),['node_free_gib'])
if __name__=='__main__':unittest.main()
