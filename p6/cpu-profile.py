#!/usr/bin/env python3
"""Extend the frozen P5 profile using its already-verified Microsoft PDB dump."""
import argparse,hashlib,json,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('pdb_directory',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
r=a.pdb_directory;profile=json.loads((r/'profile.json').read_text())
with (r/'ntkrnlmp.pdb').open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==profile['pdb_sha256']
records={m[1]:m[2] for m in re.finditer(r'^\s*(0x[0-9A-F]+) \| (.*?)(?=^\s*0x[0-9A-F]+ \||\Z)',(r/'types.txt').read_text(),re.M|re.S)}
wanted=('Number','InitialApicId','CurrentThread','KernelTime','UserTime','CycleTime');matches=[]
for idx,record in records.items():
 if not (record.startswith('LF_STRUCTURE ') and '`_KPRCB`' in record and 'forward ref' not in record):continue
 fieldlist=re.search(r'field list: (0x[0-9A-F]+)',record)[1]
 offsets={m[1]:int(m[2]) for m in re.finditer(r'LF_MEMBER \[name = `([^`]+)`.*?offset = (\d+),',records[fieldlist])}
 if all(k in offsets for k in wanted):matches.append(dict(type_index=idx,size=int(re.search(r'sizeof (\d+)',record)[1]),fields={k:offsets[k] for k in wanted}))
assert len(matches)==1
profile['types']['_KPRCB']=matches[0]
for name in ('KeNumberProcessors','KiProcessorBlock'):
 m=re.findall(r'S_PUB32[^\n]*`'+name+r'`\n\s*flags = [^\n]*addr = (\d+):(\d+)',(r/'publics.txt').read_text())
 assert len(m)==1
 section,offset=map(int,m[0]);profile['symbols'][name]=profile['pe']['sections'][section-1]['va']+offset
a.output.write_text(json.dumps(profile,indent=2)+'\n')
