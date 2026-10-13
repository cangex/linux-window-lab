/* SPDX-License-Identifier: MIT
 * WinPE installer, restricted to the uniquely named, blank 64 GiB lab NVMe.
 */
#include <windows.h>
#include <winioctl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void fail(const char *s) {printf("P5 INSTALL FAILED: %s error=%lu\n",s,GetLastError());fflush(stdout);ExitProcess(1);}
static void run(const char *s) {
 char cmd[2048]; snprintf(cmd,sizeof(cmd),"cmd.exe /c %s",s);
 STARTUPINFOA si={.cb=sizeof(si)};PROCESS_INFORMATION pi;
 printf("P5 RUN %s\n",s);fflush(stdout);
 if(!CreateProcessA(NULL,cmd,NULL,NULL,TRUE,0,NULL,NULL,&si,&pi))fail("CreateProcess");
 WaitForSingleObject(pi.hProcess,INFINITE);DWORD code;GetExitCodeProcess(pi.hProcess,&code);
 CloseHandle(pi.hThread);CloseHandle(pi.hProcess);if(code)fail("command failed");
}
int main(void) {
 int target=-1; char path[128],iso=0;DWORD got;
 setvbuf(stdout,NULL,_IONBF,0);
 for(int i=0;i<16;i++) {
  snprintf(path,sizeof(path),"\\\\.\\PhysicalDrive%d",i);
  HANDLE h=CreateFileA(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
  if(h==INVALID_HANDLE_VALUE)continue;
  STORAGE_PROPERTY_QUERY q={.PropertyId=StorageDeviceProperty,.QueryType=PropertyStandardQuery};
  unsigned char buf[4096];GET_LENGTH_INFORMATION len;
  int ok=DeviceIoControl(h,IOCTL_STORAGE_QUERY_PROPERTY,&q,sizeof(q),buf,sizeof(buf),&got,NULL);
  STORAGE_DEVICE_DESCRIPTOR *d=(void*)buf;
  if(ok && d->BusType==BusTypeNvme && d->SerialNumberOffset && d->SerialNumberOffset<got &&
     !strncmp((char*)buf+d->SerialNumberOffset,"LWLABP5INSTALL",14) &&
     DeviceIoControl(h,IOCTL_DISK_GET_LENGTH_INFO,NULL,0,&len,sizeof(len),&got,NULL) &&
     len.Length.QuadPart==64LL*1024*1024*1024) {
   unsigned char sector[512];DWORD n;
   if(!ReadFile(h,sector,sizeof(sector),&n,NULL)||n!=512)fail("read target");
   for(unsigned j=0;j<sizeof(sector);j++)if(sector[j])fail("target is not blank");
   if(target!=-1)fail("ambiguous target");
   target=i;
  }
  CloseHandle(h);
 }
 if(target<0)fail("unique blank lab NVMe absent");
 for(char c='C';c<='Z';c++) {
  snprintf(path,sizeof(path),"%c:\\sources\\install.wim",c);
  if(GetFileAttributesA(path)!=INVALID_FILE_ATTRIBUTES) {if(iso)fail("ambiguous install.wim");iso=c;}
 }
 if(!iso)fail("official install.wim absent");
 FILE *f=fopen("X:\\diskpart-p5.txt","w");if(!f)fail("script");
 fprintf(f,"select disk %d\nclean\nconvert gpt\ncreate partition efi size=260\nformat quick fs=fat32 label=LWLABESP\nassign letter=S\ncreate partition msr size=16\ncreate partition primary\nformat quick fs=ntfs label=LWLABWIN\nassign letter=W\n",target);fclose(f);
 run("diskpart /s X:\\diskpart-p5.txt");
 snprintf(path,sizeof(path),"dism /Apply-Image /ImageFile:%c:\\sources\\install.wim /Index:1 /ApplyDir:W:\\",iso);run(path);
 run("bcdboot W:\\Windows /s S: /f UEFI");
 run("bcdedit /store S:\\EFI\\Microsoft\\Boot\\BCD /set {default} hypervisorlaunchtype off");
 run("mkdir W:\\Windows\\Panther");
 run("copy /y X:\\LWLAB\\unattend.xml W:\\Windows\\Panther\\unattend.xml");
 run("mkdir W:\\LWLAB");run("copy /y X:\\LWLAB\\lw*.exe W:\\LWLAB\\");
 run("copy /y X:\\LWLAB\\lw*.dll W:\\LWLAB\\");
 run("mkdir W:\\Windows\\Setup\\Scripts");
 run("copy /y X:\\LWLAB\\SetupComplete.cmd W:\\Windows\\Setup\\Scripts\\SetupComplete.cmd");
 run("reg load HKLM\\LWP5 W:\\Windows\\System32\\config\\SYSTEM");
 run("reg add HKLM\\LWP5\\ControlSet001\\Control\\DeviceGuard /v EnableVirtualizationBasedSecurity /t REG_DWORD /d 0 /f");
 run("reg unload HKLM\\LWP5");
 puts("P5 INSTALL COMPLETE; powering off ordinary installer VM");Sleep(3000);run("wpeutil shutdown");return 0;
}
