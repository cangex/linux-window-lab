import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('gate',Path(__file__).with_name('resource-gate.py'));g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
def sample(t):
 return dict(time=t,policy=g.POLICY,reasons=[],available_gib=300,free_gib=200,disk_free_gib=100,psi_some_avg10=0,node_free_gib={n:20 for n in g.SELECTED_NODES})
class Gate(unittest.TestCase):
 def test_stability_requires_continuous_window(self):
  rows=[sample(t) for t in range(0,601,60)]
  self.assertTrue(g.stable(rows,600))
  self.assertFalse(g.stable(rows[1:],600))
  self.assertFalse(g.stable(rows[:3]+rows[5:],600))
  self.assertFalse(g.stable(rows,800))
  rows[4]['reasons']=['pressure'];self.assertFalse(g.stable(rows,600))
 def test_failure_outside_window_does_not_extend_it(self):
  rows=[dict(time=-60,reasons=['pressure'])]+[sample(t) for t in range(0,601,60)]
  self.assertTrue(g.stable(rows,600))
  rows[1]['reasons']=['pressure'];self.assertFalse(g.stable(rows,600))
 def test_node_pressure_blocks_even_with_global_headroom(self):
  row=sample(0);row['node_free_gib']['node0']=3
  self.assertEqual(g.assess(row),['node_free_gib'])
 def test_unused_nodes_do_not_block(self):
  row=sample(0);row['node_free_gib'].update(node4=0.1,node5=0.1,node6=0.1,node7=0.1)
  self.assertEqual(g.assess(row),[])
 def test_missing_selected_node_blocks(self):
  row=sample(0);del row['node_free_gib']['node3']
  self.assertEqual(g.assess(row),['node_free_gib'])
 def test_old_policy_or_mislabelled_samples_block(self):
  rows=[sample(t) for t in range(0,601,60)]
  rows[4]['policy']='p6-selected-numa-v2';self.assertFalse(g.stable(rows,600))
  rows[4]['policy']=g.POLICY;rows[4]['node_free_gib']['node2']=1
  self.assertFalse(g.stable(rows,600))
if __name__=='__main__':unittest.main()
