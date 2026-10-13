#!/usr/bin/env python3
"""Freeze only offsets actually present in the matching Microsoft kernel PDB."""
import argparse,hashlib,json,re,struct,subprocess,uuid,shutil
from pathlib import Path
def pe_info(data):
 pe=struct.unpack_from('<I',data,0x3c)[0];assert data[:2]==b'MZ' and data[pe:pe+4]==b'PE\0\0'
 machine,count,stamp=struct.unpack_from('<HHI',data,pe+4);assert machine==0x8664
 opt=pe+24;assert struct.unpack_from('<H',data,opt)[0]==0x20b
 size=struct.unpack_from('<I',data,opt+56)[0];checksum=struct.unpack_from('<I',data,opt+64)[0]
 optsize=struct.unpack_from('<H',data,pe+20)[0]
 sections=[]
 for n in range(count):
  off=opt+optsize+40*n;vsize,va,rawsize,rawptr=struct.unpack_from('<IIII',data,off+8)
  sections.append(dict(va=va,vsize=vsize,rawsize=rawsize,rawptr=rawptr))
 def raw(rva):
  for s in sections:
   if s['va']<=rva<s['va']+s['rawsize']:return rva-s['va']+s['rawptr']
  raise ValueError('RVA outside raw sections')
 debug,debugsize=struct.unpack_from('<II',data,opt+112+6*8)
 identity=None
 for off in range(raw(debug),raw(debug)+debugsize,28):
  kind,length,rva,pointer=struct.unpack_from('<IIII',data,off+12)
  if kind==2 and data[pointer:pointer+4]==b'RSDS':
   guid=str(uuid.UUID(bytes_le=data[pointer+4:pointer+20]));age=struct.unpack_from('<I',data,pointer+20)[0]
   name=data[pointer+24:pointer+length].split(b'\0')[0].decode().replace('\\','/').split('/')[-1]
   identity=dict(guid=guid,age=age,name=name,key=guid.replace('-','').upper()+format(age,'X'),rsds_rva=rva)
 assert identity
 return dict(timestamp=stamp,size=size,checksum=checksum,sections=sections,pdb=identity)
def dbi_age(data):
 # Public symbol stripping can advance PDB Info age while the DBI age remains
 # the matching executable's RSDS age. Verify the GUID and DBI age together.
 assert data.startswith(b'Microsoft C/C++ MSF 7.00')
 bs,_,_,n,_,mapping=struct.unpack_from('<6I',data,32)
 blocks=struct.unpack_from('<'+str((n+bs-1)//bs)+'I',data,mapping*bs)
 directory=b''.join(data[b*bs:(b+1)*bs] for b in blocks)[:n]
 count=struct.unpack_from('<I',directory)[0];sizes=struct.unpack_from('<'+str(count)+'I',directory,4);pos=4+count*4
 for i,size in enumerate(sizes):
  count=0 if size==0xffffffff else (size+bs-1)//bs
  blocks=struct.unpack_from('<'+str(count)+'I',directory,pos);pos+=count*4
  if i==3:
   stream=b''.join(data[b*bs:(b+1)*bs] for b in blocks)[:size]
   signature,version,age=struct.unpack_from('<3I',stream)
   assert signature==0xffffffff and version==19990903
   return age
 raise ValueError('DBI stream absent')
def main():
 p=argparse.ArgumentParser();p.add_argument('kernel',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 tool=shutil.which('llvm-pdbutil') or shutil.which('llvm-pdbutil-18')
 assert tool,'llvm-pdbutil missing'
 a.output.mkdir(parents=True,exist_ok=True);info=pe_info(a.kernel.read_bytes());pdb=info['pdb'];out=a.output
 url=f"https://msdl.microsoft.com/download/symbols/{pdb['name']}/{pdb['key']}/{pdb['name']}"
 target=out/pdb['name']
 if not target.exists():subprocess.run(['curl','--fail','--location','--retry','4','--output',str(target),url],check=True)
 for kind in ('summary','publics','types'):
  with (out/f'{kind}.txt').open('w') as f:subprocess.run([tool,'dump','-'+kind,str(target)],stdout=f,check=True)
 summary=(out/'summary.txt').read_text()
 assert pdb['guid'].upper() in summary.upper() and dbi_age(target.read_bytes())==pdb['age']
 pdb['info_age']=int(re.search(r'Age:\s*(\d+)',summary)[1]);pdb['dbi_age']=pdb['age']
 records={m[1]:m[2] for m in re.finditer(r'^\s*(0x[0-9A-F]+) \| (.*?)(?=^\s*0x[0-9A-F]+ \||\Z)',(out/'types.txt').read_text(),re.M|re.S)}
 wanted={'_EPROCESS':['Pcb','UniqueProcessId','ActiveProcessLinks','ImageFileName','CreateTime','Peb'],
  '_KPROCESS':['DirectoryTableBase'],'_PEB':['Ldr'],'_PEB_LDR_DATA':['InLoadOrderModuleList'],
  '_LDR_DATA_TABLE_ENTRY':['InLoadOrderLinks','DllBase','SizeOfImage','BaseDllName'],
  '_KLDR_DATA_TABLE_ENTRY':['InLoadOrderLinks','DllBase','SizeOfImage','BaseDllName']}
 types={}
 for name,fields in wanted.items():
  matches=[(idx,r) for idx,r in records.items() if r.startswith('LF_STRUCTURE ') and re.search(r'`'+name+'`',r) and 'forward ref' not in r]
  assert len(matches)==1,(name,len(matches))
  idx,r=matches[0];fieldlist=re.search(r'field list: (0x[0-9A-F]+)',r)[1]
  offsets={m[1]:int(m[2]) for m in re.finditer(r'LF_MEMBER \[name = `([^`]+)`.*?offset = (\d+),',records[fieldlist])}
  types[name]=dict(type_index=idx,size=int(re.search(r'sizeof (\d+)',r)[1]),fields={f:offsets[f] for f in fields})
 symbols={}
 wanted_symbols={'PsActiveProcessHead','PsInitialSystemProcess','PsLoadedModuleList','NtBuildNumber'}
 for m in re.finditer(r'S_PUB32[^\n]*`([^`]+)`\n\s*flags = [^\n]*addr = (\d+):(\d+)',(out/'publics.txt').read_text()):
  if m[1] in wanted_symbols:symbols[m[1]]=info['sections'][int(m[2])-1]['va']+int(m[3])
 assert set(symbols)==wanted_symbols,symbols
 sha=lambda f:hashlib.file_digest(f.open('rb'),'sha256').hexdigest()
 profile=dict(version=1,kernel_sha256=sha(a.kernel),pdb_sha256=sha(target),pdb_url=url,pe=info,types=types,symbols=symbols,
  tool=subprocess.check_output([tool,'--version'],text=True).strip())
 (out/'profile.json').write_text(json.dumps(profile,indent=2)+'\n');print(out/'profile.json')
if __name__=='__main__':main()
