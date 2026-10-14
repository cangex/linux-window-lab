#!/usr/bin/env python3
"""Keyboard/console setup of the ordinary P6 activation VM only (not evidence)."""
import argparse,json,subprocess,time
p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
g.add_argument('--text');g.add_argument('--keys',nargs='+');g.add_argument('--screen');a=p.parse_args()
def qmp(command,args):
 r=subprocess.check_output(['sudo','-n','virsh','qemu-monitor-command','lwlab-p6-activation',
  json.dumps(dict(execute=command,arguments=args))],text=True)
 result=json.loads(r)
 if 'error' in result:raise RuntimeError(result)
def keys(names):qmp('send-key',{'keys':[dict(type='qcode',data=n) for n in names],'hold-time':30});time.sleep(.07)
if a.screen:qmp('screendump',{'filename':a.screen})
elif a.keys:keys(a.keys)
else:
 plain={' ':'spc','\n':'ret','.':'dot',',':'comma','/':'slash','\\':'backslash',';':'semicolon',"'":'apostrophe','-':'minus','=':'equal','[':'bracket_left',']':'bracket_right','`':'grave'}
 shifted={':':'semicolon','"':'apostrophe','_':'minus','+':'equal','<':'comma','>':'dot','?':'slash','|':'backslash','{':'bracket_left','}':'bracket_right','~':'grave'}
 shifted.update(dict(zip('!@#$%^&*()','1234567890')))
 for c in a.text:
  if c in shifted:keys(['shift',shifted[c]])
  elif c.isascii() and c.isupper():keys(['shift',c.lower()])
  elif c in plain:keys([plain[c]])
  elif c.isascii() and c.isalnum():keys([c])
  else:raise ValueError(f'unsupported console character: {c!r}')
