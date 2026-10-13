/* SPDX-License-Identifier: MIT */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "record.h"
static void publish(struct lw_record *r,uint64_t seq,uint32_t state,int torn) {
 InterlockedExchange64((volatile LONG64 *)&r->sequence,(LONG64)(seq-1));
 r->state=state;
 for(unsigned i=0;i<LW_PAYLOAD_BYTES/8;i++) {
  uint64_t value=lw_word(r->nonce,r->epoch,seq,i);
  memcpy(r->payload+i*8,&value,8);
  if(torn && i==LW_PAYLOAD_BYTES/16) Sleep(50);
 }
 r->checksum=lw_hash(r->payload,LW_PAYLOAD_BYTES);
 r->tail=seq;
 MemoryBarrier();
 InterlockedExchange64((volatile LONG64 *)&r->sequence,(LONG64)seq);
}
int main(void) {
 FILETIME ft; LARGE_INTEGER counter;
 GetSystemTimeAsFileTime(&ft);QueryPerformanceCounter(&counter);
 uint64_t nonce=(((uint64_t)ft.dwHighDateTime<<32)|ft.dwLowDateTime) ^ (uint64_t)counter.QuadPart;
 for(uint64_t epoch=1;;epoch++) {
  struct lw_record *r=VirtualAlloc(NULL,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
  if(!r || !VirtualLock(r,4096)) { printf("LW4 lock failed %lu\n",GetLastError());return 2; }
  memcpy(r->magic,LW_RECORD_MAGIC,16);r->version=1;r->length=4096;
  r->nonce=nonce;r->epoch=epoch;r->bytes=LW_PAYLOAD_BYTES;r->pid=GetCurrentProcessId();
  uint64_t seq=2,start=GetTickCount64();
  printf("LW4 allocated nonce=%016llx epoch=%llu va=%p pid=%lu\n",
     (unsigned long long)nonce,(unsigned long long)epoch,r,GetCurrentProcessId());fflush(stdout);
  for(;;seq+=2) {
   uint64_t elapsed=GetTickCount64()-start;
   if(elapsed>=25000) break;
   publish(r,seq,1,elapsed>=10000 && elapsed<20000);
   Sleep(1);
  }
  publish(r,seq,2,0);
  printf("LW4 revoked epoch=%llu sequence=%llu\n",(unsigned long long)epoch,(unsigned long long)seq);fflush(stdout);
  Sleep(3000); /* Reader has a bounded observation window for the tombstone. */
  VirtualUnlock(r,4096);VirtualFree(r,0,MEM_RELEASE);Sleep(1000);
 }
}
