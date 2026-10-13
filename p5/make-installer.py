#!/usr/bin/env python3
"""Official ADK WinPE plus disk-restricted lab installer and truth programs."""
import argparse,hashlib,json,secrets,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('p3_media',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
assert not a.output.exists();a.output.mkdir(parents=True)
here=Path(__file__).resolve().parent
run=lambda *args,**kw:subprocess.run(list(map(str,args)),check=True,**kw)
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
media=a.output/'media';shutil.copytree(a.p3_media/'media',media)
extra=a.output/'LWLAB';extra.mkdir()
for source,name,flags in [('install.c','lwinstall.exe',[]),('truth.c','lwtruth.exe',['-ladvapi32']),('child.c','lwchild.exe',[]),('lifecycle.c','lwlifecycle.dll',['-shared'])]:
 run('x86_64-w64-mingw32-gcc','-O2','-Wall','-Wextra','-Werror','-static',here/source,*flags,'-o',extra/name)
password=secrets.token_hex(16)+'aA1!'
(extra/'unattend.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
 <settings pass="specialize"><component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS"><ComputerName>LWLAB-P5</ComputerName><TimeZone>UTC</TimeZone></component></settings>
 <settings pass="oobeSystem">
  <component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS"><InputLocale>en-US</InputLocale><SystemLocale>en-US</SystemLocale><UILanguage>en-US</UILanguage><UserLocale>en-US</UserLocale></component>
  <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
   <OOBE><HideEULAPage>true</HideEULAPage><HideOnlineAccountScreens>true</HideOnlineAccountScreens><HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE><ProtectYourPC>3</ProtectYourPC></OOBE>
   <UserAccounts><LocalAccounts><LocalAccount wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"><Name>lwlab</Name><Group>Administrators</Group><Password><Value>'''+password+'''</Value><PlainText>true</PlainText></Password></LocalAccount></LocalAccounts></UserAccounts>
   <AutoLogon><Username>lwlab</Username><Enabled>true</Enabled><LogonCount>3</LogonCount><Password><Value>'''+password+'''</Value><PlainText>true</PlainText></Password></AutoLogon>
  </component>
 </settings>
</unattend>
''')
(extra/'unattend.xml').chmod(0o600)
(extra/'SetupComplete.cmd').write_bytes(b'@echo off\r\nschtasks /create /tn LWLAB-P5 /sc onstart /ru SYSTEM /rl HIGHEST /tr C:\\LWLAB\\lwtruth.exe /f\r\nschtasks /run /tn LWLAB-P5\r\n')
start=a.output/'startnet.cmd';start.write_bytes(b'@echo off\r\nwpeinit\r\nX:\\LWLAB\\lwinstall.exe\r\n')
wim=media/'sources/boot.wim'
run('wimlib-imagex','update',wim,'1',input=f'add "{extra.resolve()}" /LWLAB\nadd "{start.resolve()}" /Windows/System32/startnet.cmd\n',text=True)
fat=a.output/'installer-fat.img'
with fat.open('xb') as f:f.truncate(512*1024*1024)
run('mkfs.vfat','-F','32','-n','LWPEP5',fat)
run('mcopy','-s','-i',fat,*sorted(media.iterdir()),'::/')
run('python3',here.parent/'p3/wrap-gpt.py',fat,a.output/'installer-gpt.img')
(a.output/'media.json').write_text(json.dumps(dict(p3_manifest_sha256=sha(a.p3_media/'media.json'),fat_sha256=sha(fat),binaries={x.name:sha(x) for x in extra.iterdir() if x.suffix in ('.exe','.dll')}),indent=2)+'\n')
