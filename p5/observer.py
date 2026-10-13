#!/usr/bin/env python3
"""Read-only, version-pinned Windows semantics through the main Linux kernel.

No QMP RAM reads, /dev/mem, Windows debug ports, or helper-provided addresses.
Live lists are revalidated, not advertised as an atomic whole-system snapshot.
"""
import argparse,ctypes,fcntl,json,os,struct,time,uuid
from pathlib import Path
MASK=(1<<52)-4096
class Unavailable(Exception):pass
class Changed(Unavailable):pass
class Physical:
 def __init__(self,path='/dev/lwobserve'):
  self.fd=os.open(path,os.O_RDONLY);buf=bytearray(96);fcntl.ioctl(self.fd,0x80605740,buf,True)
  version,self.generation,count,self.maximum=struct.unpack_from('<4Q',buf)
  if version!=2 or count!=4:raise ValueError('P5 backend ABI required')
  self.extents=[struct.unpack_from('<QQ',buf,32+i*16) for i in range(count)]
  self.buffer=ctypes.create_string_buffer(self.maximum);self.calls=0;self.bytes=0
 def owns(self,a,n):return n>0 and any(a>=b and a-b<s and n<=s-(a-b) for b,s in self.extents)
 def read(self,a,n):
  if not self.owns(a,n):raise Unavailable(f'physical outside partition: {a:x}+{n:x}')
  if n>self.maximum:return b''.join(self.read(a+i,min(n-i,self.maximum)) for i in range(0,n,self.maximum))
  req=struct.pack('<4Q',self.generation,a,n,ctypes.addressof(self.buffer))
  fcntl.ioctl(self.fd,0x40205741,req);self.calls+=1;self.bytes+=n
  return ctypes.string_at(self.buffer,n)
 def u64(self,a):return struct.unpack('<Q',self.read(a,8))[0]
 def chunks(self):
  for base,size in self.extents:
   for off in range(0,size,self.maximum):yield base+off,self.read(base+off,min(self.maximum,size-off))
class Virtual:
 def __init__(self,physical,cr3):self.p=physical;self.cr3=cr3&MASK
 @staticmethod
 def canonical(va):return 0<=va<1<<64 and va>>48==(0xffff if va&(1<<47) else 0)
 def walk(self,va):
  if not self.canonical(va):raise Unavailable('noncanonical VA')
  table=self.cr3;trace=[]
  for shift in (39,30,21,12):
   address=table+((va>>shift)&511)*8;entry=self.p.u64(address);trace.append((address,entry))
   if not entry&1:raise Unavailable('nonresident or invalid PTE')
   if shift==39 and entry&128:raise Unavailable('reserved PML4 PS')
   if shift==12 or entry&128:
    if shift!=12 and (entry&MASK&((1<<shift)-1)&~4096):raise Unavailable('misaligned large page')
    pa=(entry&MASK&~((1<<shift)-1))+(va&((1<<shift)-1))
    if not self.p.owns(pa,1):raise Unavailable('translated page outside partition')
    return pa,trace,shift
   table=entry&MASK
  raise AssertionError('page walk')
 def read(self,va,n):
  if n<0 or n>1<<20:raise ValueError('bounded virtual read required')
  for _ in range(3):
   result=[];traces=[];left=n;at=va
   while left:
    pa,trace,_=self.walk(at);take=min(left,4096-(at&4095));result.append(self.p.read(pa,take));traces+=trace;at+=take;left-=take
   # Accessed/dirty bit changes do not alter translation. No persistent PTE cache.
   if all((self.p.u64(a)^v)&~0x60==0 for a,v in traces):return b''.join(result)
  raise Changed('page tables changed while reading')
 def u64(self,a):return struct.unpack('<Q',self.read(a,8))[0]
 def u32(self,a):return struct.unpack('<I',self.read(a,4))[0]
 def string(self,a):
  length,maximum,_,buffer=struct.unpack('<HHIQ',self.read(a,16))
  if length>maximum or length>1024 or length%2:raise Unavailable('invalid UNICODE_STRING')
  return self.read(buffer,length).decode('utf-16-le')
def field(profile,typ,name):return profile['types'][typ]['fields'][name]
def bootstrap(physical,profile):
 pe=profile['pe'];kernels=[]
 # A header is only a candidate; GUID and kernel-global linkage are checked later.
 for base,block in physical.chunks():
  at=block.find(b'MZ')
  while at>=0:
   if not (base+at)&4095 and at+0x200<len(block):
    pos=struct.unpack_from('<I',block,at+0x3c)[0]
    if pos<0x180 and block[at+pos:at+pos+4]==b'PE\0\0':
     opt=at+pos+24
     stamp=struct.unpack_from('<I',block,at+pos+8)[0];size=struct.unpack_from('<I',block,opt+56)[0]
     if stamp==pe['timestamp'] and size==pe['size']:
      va=struct.unpack_from('<Q',block,opt+24)[0]
      if va>>48==0xffff:kernels.append((base+at,va))
   at=block.find(b'MZ',at+2)
 if not kernels:raise Unavailable('pinned kernel PE not resident')
 nameoff=field(profile,'_EPROCESS','ImageFileName');pidoff=field(profile,'_EPROCESS','UniqueProcessId')
 dtb=field(profile,'_EPROCESS','Pcb')+field(profile,'_KPROCESS','DirectoryTableBase')
 for base,block in physical.chunks():
  at=block.find(b'System\0')
  while at>=0:
   obj=base+at-nameoff
   try:
    if obj%16==0 and physical.u64(obj+pidoff)==4:
     cr3=physical.u64(obj+dtb);v=Virtual(physical,cr3)
     for pa,kernel in kernels:
      if v.walk(kernel)[0]!=pa:continue
      system=v.u64(kernel+profile['symbols']['PsInitialSystemProcess'])
      if v.walk(system)[0]!=obj or v.u64(system+pidoff)!=4:continue
      rsds=v.read(kernel+pe['pdb']['rsds_rva'],24)
      expected=b'RSDS'+uuid.UUID(pe['pdb']['guid']).bytes_le+struct.pack('<I',pe['pdb']['age'])
      if rsds!=expected:continue
      return dict(kernel=kernel,system=system,cr3=cr3,generation=physical.generation,
       build=v.u32(kernel+profile['symbols']['NtBuildNumber'])&0xffff,pdb=pe['pdb']['key'])
   except Unavailable:pass
   at=block.find(b'System\0',at+1)
 raise Unavailable('System process/kernel linkage not found')
def walk_list(v,head,offset,read_item,limit=4096):
 for _ in range(3):
  try:
   first=v.read(head,16);next_,last=struct.unpack('<QQ',first);prev=head;seen=set();rows=[];links=[]
   while next_!=head:
    if next_ in seen or len(seen)>=limit or not Virtual.canonical(next_):raise Changed('invalid/cyclic list')
    seen.add(next_);pair=v.read(next_,16);forward,back=struct.unpack('<QQ',pair)
    if back!=prev:raise Changed('list backlink changed')
    rows.append(read_item(next_-offset));links.append((next_,pair));prev=next_;next_=forward
   if prev!=last or v.read(head,16)!=first:raise Changed('list head changed')
   if any(v.read(a,16)!=pair for a,pair in links):raise Changed('list changed during traversal')
   return rows
  except Changed:continue
 raise Changed('unstable list after retries')
def processes(p,profile,boot):
 v=Virtual(p,boot['cr3']);o=profile['types']['_EPROCESS']['fields']
 def item(a):
  before=v.read(a+o['UniqueProcessId'],8);pid=struct.unpack('<Q',before)[0]
  created=v.u64(a+o['CreateTime']);name=v.read(a+o['ImageFileName'],15).split(b'\0')[0].decode('ascii','strict')
  cr3=v.u64(a+o['Pcb']+field(profile,'_KPROCESS','DirectoryTableBase'));peb=v.u64(a+o['Peb'])
  if v.read(a+o['UniqueProcessId'],8)!=before or v.u64(a+o['CreateTime'])!=created:raise Changed('process identity changed')
  return dict(pid=pid,name=name,created=created,address=a,cr3=cr3,peb=peb,generation=p.generation)
 return walk_list(v,boot['kernel']+profile['symbols']['PsActiveProcessHead'],o['ActiveProcessLinks'],item)
def modules(p,profile,boot,process=None):
 typ='_LDR_DATA_TABLE_ENTRY' if process else '_KLDR_DATA_TABLE_ENTRY';o=profile['types'][typ]['fields']
 v=Virtual(p,process['cr3'] if process else boot['cr3'])
 if process:
  if not process['peb']:raise Unavailable('no native PEB')
  ldr=v.u64(process['peb']+field(profile,'_PEB','Ldr'));head=ldr+field(profile,'_PEB_LDR_DATA','InLoadOrderModuleList')
 else:head=boot['kernel']+profile['symbols']['PsLoadedModuleList']
 def item(a):return dict(name=v.string(a+o['BaseDllName']),base=v.u64(a+o['DllBase']),size=v.u32(a+o['SizeOfImage']))
 return walk_list(v,head,o['InLoadOrderLinks'],item)
class TruthReader:
 # Cooperative page is only a truth comparator; bootstrap never receives it.
 def __init__(self,p):self.p=p;self.address=None
 def read(self):
  p=self.p
  if self.address is None:
   for base,block in p.chunks():
    at=block.find(b'LWLAB-P5-TRUTH1\0')
    if at>=0 and (base+at)%4096==0:
     self.address=base+at;break
   if self.address is None:raise Unavailable('no enabled truth page')
  address=self.address;first=p.u64(address+16);raw=p.read(address,4096);last=p.u64(address+16)
  if raw[:16]!=b'LWLAB-P5-TRUTH1\0':raise Unavailable('truth page retired')
  if first!=last or first!=struct.unpack_from('<Q',raw,4088)[0] or first&1:raise Changed('truth publication in flight')
  values=struct.unpack_from('<11Q',raw,16)
  if not values[-1]:raise Unavailable('truth channel disabled')
  return dict(zip(('sequence','nonce','seconds','pid','created','kernel','child','module','io','errors','enabled'),values))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('profile',type=Path);ap.add_argument('--seconds',type=int,default=60);ap.add_argument('--compare-truth',action='store_true');a=ap.parse_args()
 profile=json.loads(a.profile.read_text());p=Physical();start=time.monotonic();boot=None
 while boot is None:
  try:boot=bootstrap(p,profile)
  except Unavailable:
   if time.monotonic()-start>120:raise
   time.sleep(2)
 print(json.dumps(dict(event='bootstrap',**boot,seconds=time.monotonic()-start,address_helper_used=False)),flush=True)
 deadline=time.monotonic()+a.seconds;valid=0;unavailable=0;comparator=TruthReader(p) if a.compare_truth else None
 while time.monotonic()<deadline:
  try:
   before=comparator.read() if comparator else None
   ps=processes(p,profile,boot);ks=modules(p,profile,boot);target=next((x for x in ps if x['name'].lower()=='lwtruth.exe'),None)
   us=modules(p,profile,boot,target) if target else []
   row=dict(event='sample',time=time.time(),generation=p.generation,processes=ps,kernel_modules=ks,target_modules=us)
   if a.compare_truth:
    t=comparator.read()
    if t!=before:raise Changed('truth changed across object traversal')
    row['truth']=t
    row['matches']=bool(target and target['pid']==t['pid'] and target['created']==t['created'] and boot['kernel']==t['kernel'] and t['errors']==0 and
     any(x['pid']==t['child'] and x['name'].lower()=='lwchild.exe' for x in ps)==bool(t['child']) and
     next((x['base'] for x in us if x['name'].lower()=='lwlifecycle.dll'),0)==t['module'])
   print(json.dumps(row),flush=True);valid+=1
  except (Unavailable,UnicodeError,StopIteration) as e:
   unavailable+=1;print(json.dumps(dict(event='unavailable',reason=str(e))),flush=True)
  time.sleep(1)
 print(json.dumps(dict(event='result',valid_samples=valid,unavailable=unavailable,generation=p.generation,physical_calls=p.calls,physical_bytes=p.bytes,address_helper_used=False)),flush=True)
 return 0 if valid else 1
if __name__=='__main__':raise SystemExit(main())
