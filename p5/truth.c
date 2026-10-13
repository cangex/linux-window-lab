/* SPDX-License-Identifier: MIT
 * Cooperative truth exists for 90 s only. Thereafter the same workload keeps
 * running, but no address/marker channel remains. Disk logs are compared later.
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef LONG (WINAPI *QUERY)(ULONG,PVOID,ULONG,PULONG);
struct mod {void *section,*mapped,*base;ULONG size,flags;USHORT order,init,loads,nameoff;char name[256];};
struct mods {ULONG count;struct mod m[1];};
struct truth {
 char magic[16];uint64_t sequence,nonce,elapsed,pid,created,kernel,child,module,io_count,io_errors,enabled;
 unsigned char pad[3984];uint64_t tail;
};
_Static_assert(sizeof(struct truth)==4096,"truth page");
static uint64_t ft(FILETIME t) {return ((uint64_t)t.dwHighDateTime<<32)|t.dwLowDateTime;}
int main(void) {
 HANDLE token;TOKEN_PRIVILEGES priv={.PrivilegeCount=1};
 if(OpenProcessToken(GetCurrentProcess(),TOKEN_ADJUST_PRIVILEGES|TOKEN_QUERY,&token)) {
  LookupPrivilegeValueA(NULL,SE_DEBUG_NAME,&priv.Privileges[0].Luid);priv.Privileges[0].Attributes=SE_PRIVILEGE_ENABLED;
  AdjustTokenPrivileges(token,FALSE,&priv,0,NULL,NULL);CloseHandle(token);
 }
 uint64_t kernel=0;QUERY query=(QUERY)(void*)GetProcAddress(GetModuleHandleA("ntdll.dll"),"NtQuerySystemInformation");
 unsigned char *mods=VirtualAlloc(NULL,1<<20,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);ULONG used;
 if(query && query(11,mods,1<<20,&used)>=0 && ((struct mods*)mods)->count) kernel=(uintptr_t)((struct mods*)mods)->m[0].base;
 VirtualFree(mods,0,MEM_RELEASE);
 CreateDirectoryA("C:\\LWLAB",NULL);
 FILE *log=fopen("C:\\LWLAB\\truth.jsonl","a");if(!log)return 1;
 setvbuf(log,NULL,_IONBF,0);
 HANDLE disk=CreateFileA("C:\\LWLAB\\io.bin",GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_FLAG_WRITE_THROUGH,NULL);
 struct truth *r=VirtualAlloc(NULL,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
 if(!r||!VirtualLock(r,4096)||disk==INVALID_HANDLE_VALUE)return 2;
 FILETIME create,exit,kern,user,now;GetProcessTimes(GetCurrentProcess(),&create,&exit,&kern,&user);GetSystemTimeAsFileTime(&now);
 uint64_t nonce=ft(now),pid=GetCurrentProcessId(),created=ft(create),seq=0,io=0,errors=0;
 ULONGLONG start=GetTickCount64();PROCESS_INFORMATION child={0};HMODULE module=NULL;
 unsigned char writebuf[4096],readbuf[4096];
 for(;;) {
  uint64_t sec=(GetTickCount64()-start)/1000;
  if(child.hProcess && WaitForSingleObject(child.hProcess,0)==WAIT_OBJECT_0) {CloseHandle(child.hProcess);CloseHandle(child.hThread);memset(&child,0,sizeof(child));}
  if(sec%30<15 && !child.hProcess) {
   STARTUPINFOA si={.cb=sizeof(si)};char command[]="C:\\LWLAB\\lwchild.exe";
   if(!CreateProcessA(NULL,command,NULL,NULL,FALSE,0,NULL,NULL,&si,&child))errors++;
  }
  if(sec%20<10 && !module) module=LoadLibraryA("C:\\LWLAB\\lwlifecycle.dll");
  if(sec%20>=10 && module) {FreeLibrary(module);module=NULL;}
  for(unsigned i=0;i<sizeof(writebuf);i++)writebuf[i]=(unsigned char)(i^io);
  DWORD n;LARGE_INTEGER zero={.QuadPart=0};
  if(!SetFilePointerEx(disk,zero,NULL,FILE_BEGIN)||!WriteFile(disk,writebuf,sizeof(writebuf),&n,NULL)||n!=sizeof(writebuf)||!FlushFileBuffers(disk)||
     !SetFilePointerEx(disk,zero,NULL,FILE_BEGIN)||!ReadFile(disk,readbuf,sizeof(readbuf),&n,NULL)||n!=sizeof(readbuf)||memcmp(writebuf,readbuf,sizeof(writebuf)))errors++;
  io++;
  if(r) {
   InterlockedExchange64((volatile LONG64*)&r->sequence,++seq);
   memcpy(r->magic,"LWLAB-P5-TRUTH1",16);r->nonce=nonce;r->elapsed=sec;r->pid=pid;r->created=created;r->kernel=kernel;
   r->child=child.dwProcessId;r->module=(uintptr_t)module;r->io_count=io;r->io_errors=errors;r->enabled=sec<90;
   r->tail=++seq;MemoryBarrier();InterlockedExchange64((volatile LONG64*)&r->sequence,seq);
   if(sec>=90) {Sleep(2000);SecureZeroMemory(r,4096);VirtualUnlock(r,4096);VirtualFree(r,0,MEM_RELEASE);r=NULL;}
  }
  GetSystemTimeAsFileTime(&now);
  fprintf(log,"{\"nonce\":\"%016llx\",\"time\":%llu,\"seconds\":%llu,\"pid\":%llu,\"created\":%llu,\"kernel\":\"%016llx\",\"child\":%lu,\"module\":\"%016llx\",\"io\":%llu,\"errors\":%llu,\"helper\":%s}\n",
   (unsigned long long)nonce,(unsigned long long)ft(now),(unsigned long long)sec,(unsigned long long)pid,(unsigned long long)created,
   (unsigned long long)kernel,child.dwProcessId,(unsigned long long)(uintptr_t)module,(unsigned long long)io,(unsigned long long)errors,r?"true":"false");
  Sleep(1000);
 }
}
