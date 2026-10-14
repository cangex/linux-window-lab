"""Read Windows' own system clock using pinned PDB offsets and its user mapping.

The observer uses this only to bracket data reads. It never reads truth logs.
The user mapping is documented by Microsoft's !kuser command; layout comes from
our verified build's PDB, not a guessed structure version.
"""
SHARED_USER_DATA=0x7ffe0000
class UnstableClock(Exception):pass

def read_clock(virtual,profile,build):
 shared=profile['types']['_KUSER_SHARED_DATA']['fields']
 fields=profile['types']['_KSYSTEM_TIME']['fields']
 if virtual.u32(SHARED_USER_DATA+shared['NtBuildNumber'])&0xffff!=build:
  raise UnstableClock('shared clock build differs from discovered kernel')
 base=SHARED_USER_DATA+shared['SystemTime']
 for _ in range(4):
  hi1=virtual.u32(base+fields['High1Time'])
  lo=virtual.u32(base+fields['LowPart'])
  hi2=virtual.u32(base+fields['High2Time'])
  check=virtual.u32(base+fields['High1Time'])
  if hi1==hi2==check:return (hi1<<32)|lo
 raise UnstableClock('shared system time changed during read')
