/* SPDX-License-Identifier: MIT
 * No shared marker or address helper. Truth is written only to the owned disk.
 * Fixed-affinity workers continuously verify memory and report their CPU ID.
 */
#include <windows.h>
#include <intrin.h>
#include <io.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MAXCPU 4
struct worker {unsigned number;volatile LONG64 loops,errors;HANDLE thread;};
static struct worker workers[MAXCPU];
static uint64_t ft(FILETIME t){return ((uint64_t)t.dwHighDateTime<<32)|t.dwLowDateTime;}
static uint64_t stamp(void){_mm_lfence();uint64_t t=__rdtsc();_mm_lfence();return t;}
static DWORD WINAPI work(void *arg){
 struct worker *w=arg;SIZE_T bytes=64u<<20;
 if(!SetThreadAffinityMask(GetCurrentThread(),(DWORD_PTR)1<<w->number)){InterlockedIncrement64(&w->errors);return 1;}
 uint64_t *mem=VirtualAlloc(NULL,bytes,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
 if(!mem){InterlockedIncrement64(&w->errors);return 1;}
 for(uint64_t epoch=1;;epoch++){
  for(SIZE_T i=0;i<bytes/8;i++)mem[i]=(i*0x9e3779b97f4a7c15ULL)^epoch;
  MemoryBarrier();
  for(SIZE_T i=0;i<bytes/8;i++)if(mem[i]!=((i*0x9e3779b97f4a7c15ULL)^epoch)){InterlockedIncrement64(&w->errors);break;}
  if(GetCurrentProcessorNumber()!=w->number)InterlockedIncrement64(&w->errors);
  InterlockedIncrement64(&w->loops);Sleep(20);
 }
}
int main(void){
 SYSTEM_INFO si;GetSystemInfo(&si);unsigned cpus=si.dwNumberOfProcessors;if(!cpus||cpus>MAXCPU)return 2;
 CreateDirectoryA("C:\\LWLAB",NULL);
 FILE *log=fopen("C:\\LWLAB\\p6-truth.jsonl","a");if(!log)return 3;setvbuf(log,NULL,_IONBF,0);
 HANDLE disk=CreateFileA("C:\\LWLAB\\p6-io.bin",GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_FLAG_WRITE_THROUGH,NULL);
 if(disk==INVALID_HANDLE_VALUE)return 4;
 for(unsigned i=0;i<cpus;i++){workers[i].number=i;workers[i].thread=CreateThread(NULL,0,work,&workers[i],0,NULL);if(!workers[i].thread)return 5;}
 FILETIME now,created,exit,kern,user;GetProcessTimes(GetCurrentProcess(),&created,&exit,&kern,&user);GetSystemTimeAsFileTime(&now);
 uint64_t nonce=ft(now),pid=GetCurrentProcessId(),identity=ft(created),io=0,errors=0,events=0;ULONGLONG start=GetTickCount64();
 HMODULE module=NULL;PROCESS_INFORMATION child={0};unsigned char out[65536],in[65536];
 for(;;){
  uint64_t seconds=(GetTickCount64()-start)/1000,begin=stamp();
  if(child.hProcess&&WaitForSingleObject(child.hProcess,0)==WAIT_OBJECT_0){CloseHandle(child.hProcess);CloseHandle(child.hThread);memset(&child,0,sizeof(child));events++;}
  if(seconds%30<15&&!child.hProcess){STARTUPINFOA startup={.cb=sizeof(startup)};char command[]="C:\\LWLAB\\lwchild.exe";
   if(!CreateProcessA(NULL,command,NULL,NULL,FALSE,0,NULL,NULL,&startup,&child))errors++;else events++;}
  if(seconds%20<10&&!module){module=LoadLibraryA("C:\\LWLAB\\lwlifecycle.dll");if(!module)errors++;else events++;}
  if(seconds%20>=10&&module){if(!FreeLibrary(module))errors++;module=NULL;events++;}
  uint64_t changed=stamp();
  for(unsigned i=0;i<sizeof(out);i++)out[i]=(unsigned char)(i^io);
  DWORD n;LARGE_INTEGER zero={.QuadPart=0};
  if(!SetFilePointerEx(disk,zero,NULL,FILE_BEGIN)||!WriteFile(disk,out,sizeof(out),&n,NULL)||n!=sizeof(out)||!FlushFileBuffers(disk)||
    !SetFilePointerEx(disk,zero,NULL,FILE_BEGIN)||!ReadFile(disk,in,sizeof(in),&n,NULL)||n!=sizeof(in)||memcmp(out,in,sizeof(in)))errors++;
  io++;GetSystemTimeAsFileTime(&now);
  fprintf(log,"{\"schema\":1,\"nonce\":\"%016llx\",\"time\":%llu,\"seconds\":%llu,\"pid\":%llu,\"created\":%llu,\"child\":%lu,\"module\":%llu,\"io\":%llu,\"errors\":%llu,\"events\":%llu,\"tsc_before\":%llu,\"tsc_after\":%llu,\"helper\":false,\"cpus\":[",
   (unsigned long long)nonce,(unsigned long long)ft(now),(unsigned long long)seconds,(unsigned long long)pid,(unsigned long long)identity,
   child.dwProcessId,(unsigned long long)(uintptr_t)module,(unsigned long long)io,(unsigned long long)errors,(unsigned long long)events,
   (unsigned long long)begin,(unsigned long long)changed);
  for(unsigned i=0;i<cpus;i++)fprintf(log,"%s{\"cpu\":%u,\"loops\":%llu,\"errors\":%llu}",i?",":"",i,
   (unsigned long long)InterlockedCompareExchange64(&workers[i].loops,0,0),(unsigned long long)InterlockedCompareExchange64(&workers[i].errors,0,0));
  fprintf(log,"]}\n");
  /* Unbuffered stdio does not make NTFS data/length durable across a forced
   * partition stop. Commit each complete truth record before the next epoch. */
  if(fflush(log)||!FlushFileBuffers((HANDLE)_get_osfhandle(_fileno(log))))return 6;
  Sleep(1000);
 }
}
