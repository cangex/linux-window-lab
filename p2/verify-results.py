#!/usr/bin/env python3
"""Recheck all raw TCP samples and final mailboxes, independent of the runner."""
import argparse,json,re,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--cycles',type=int,default=10);a=p.parse_args()
m=json.loads((a.directory/'matrix.json').read_text());assert m['pass'] and len(m['runs'])==a.cycles
ids=set();generations=set();total=0;gap=0
for i,r in enumerate(m['runs']):
 assert r['pass'] and r['persistent_tcp'] and r['ping_failures']==0
 assert r['boot_id'] not in ids;ids.add(r['boot_id'])
 guest=r['guest'];gen=guest['generation'];assert gen not in generations;generations.add(gen)
 assert guest['kernel_taint']==0 and 'port:000002F8' not in guest['serial_ports']
 assert guest['pass'] and guest['start_errno'] is None and guest['flags']==0
 assert guest['seconds_after_start'] >= (300 if i==0 else 30)
 lines=[json.loads(x) for x in (a.directory/r['name']/'stream.jsonl').read_text().splitlines()]
 samples=[x for x in lines if x['kind']=='sample'];assert samples and lines[-1]['kind']=='result'
 assert any(not x['launched'] for x in samples) and any(x.get('launch_pending') for x in samples)
 hbs=[];times=[];ready_times=[]
 for n,x in enumerate(samples):
  assert x['boot_id']==r['boot_id'] and x['sequence']==n and x['io_ok']
  data=(f"{r['boot_id']}:{gen}:{n}\n".encode()*128)
  assert hashlib.sha256(data).hexdigest()==x['io_sha256']
  times.append(x['received_monotonic'])
  if x['launched']:
   s=x['state'];assert s['state']=='payload-ready' and int(s['stage'])==2 and int(s['phase'])==9
   assert int(s['checks'],0)==511 and int(s['payload_error'])==0 and int(s['failed_case'],0)==0
   assert int(s['ack_generation'])==gen and int(s['actual_apic'])==int(s['expected_apic'])==4
   assert int(s['cr3'],0)==0x40002000 and int(s['stack'],0)==0x42400000
   assert int(s['ack_magic'],0)==0x313030765041574c and int(s['timer_ticks'])>=200
   assert 0x40000000<=int(s['alloc_low'],0)<int(s['alloc_high'],0)<=0x50000000
   assert int(s['rsdp'],0)==0x42200000 and 0x40000000<=int(s['system_table'],0)<0x50000000
   hbs.append(int(s['heartbeat']));ready_times.append(x['monotonic'])
 assert len(hbs)>=guest['seconds_after_start']-1 and all(b>a for a,b in zip(hbs,hbs[1:]))
 assert ready_times[-1]-ready_times[0]>=guest['seconds_after_start']-2
 gaps=[b-a for a,b in zip(times,times[1:])];assert max(gaps)<8
 gap=max(gap,max(gaps));total+=len(samples)
 for name,c in guest['negative_checks'].items():assert c['errno']==(16 if name in ['online_cpu','second_start','reload_after_start','reonline_after_start'] else 34 if name in ['outside_memory','wrong_size','illegal_entry','entry_outside'] else 22),(name,c)
 dmesg=(a.directory/f"{r['name']}-dmesg.log").read_text()
 assert not re.search(r'BUG:|WARNING:|Oops:|Kernel panic',dmesg)
 assert 'IPI shorthand broadcast: disabled' in dmesg
 assert 'AP kick cleanup complete' in dmesg
 uefi=(a.directory/f"{r['name']}-uefi.log").read_text(errors='replace')
 assert all(f'LWLAB CHECK {bit} PASS' in uefi for bit in range(7))
 assert 'ASSERT [' not in uefi and 'Exception Type' not in uefi
print(json.dumps({'pass':True,'cold_boots':len(ids),'efi_checks_per_boot':9,'samples':total,'max_tcp_gap_seconds':gap,'long_seconds':m['runs'][0]['guest']['seconds_after_start']},indent=2))
