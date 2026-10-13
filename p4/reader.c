/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>
#include "lwobserve.h"
#include "record.h"
static int fd;
static struct lwobs_info info;
static uint64_t attempts,accepted,busy,torn,revoked,invalid,wrong,epochs;
static uint64_t hist[64], seq_min=UINT64_MAX,seq_max;
static double now(clockid_t c) {struct timespec t;clock_gettime(c,&t);return t.tv_sec+t.tv_nsec/1e9;}
static int readmem(uint64_t address,void *out,size_t n,uint64_t gen) {
 struct lwobs_read request={gen,address,n,(uintptr_t)out};return ioctl(fd,LWOBS_READ,&request);
}
static void must_read(uint64_t address,void *out,size_t n) {
 if(readmem(address,out,n,info.generation)) {perror("LWOBS_READ");exit(3);}
}
static int check(const struct lw_record *r,uint64_t first,uint64_t last) {
 if(first&1) return 1;
 if(first!=last || first!=r->sequence || first!=r->tail) return 2;
 if(memcmp(r->magic,LW_RECORD_MAGIC,16) || r->version!=1 || r->length!=4096 ||
    !r->nonce || !r->epoch || r->bytes!=LW_PAYLOAD_BYTES || !r->pid || r->reserved) return 4;
 if(r->state==2) return 3;
 if(r->state!=1) return 4;
 if(lw_hash(r->payload,LW_PAYLOAD_BYTES)!=r->checksum) return 5;
 for(unsigned i=0;i<LW_PAYLOAD_BYTES/8;i++) {
  uint64_t v;memcpy(&v,r->payload+i*8,8);
  if(v!=lw_word(r->nonce,r->epoch,r->sequence,i)) return 5;
 }
 return 0;
}
static int snapshot(uint64_t pa,struct lw_record *r) {
 uint64_t first,last;must_read(pa+32,&first,8);
 if(first&1) return 1;
 must_read(pa,r,sizeof(*r));must_read(pa+32,&last,8);
 return check(r,first,last);
}
static uint64_t locate(uint64_t old_nonce,uint64_t old_epoch) {
 unsigned char *buf=malloc(1<<20);if(!buf)exit(3);
 for(unsigned e=0;e<info.count;e++) for(uint64_t off=0;off<info.extent[e].bytes;off+=1<<20) {
  size_t n=info.extent[e].bytes-off;if(n>1<<20)n=1<<20;
  uint64_t pa=info.extent[e].base+off;must_read(pa,buf,n);
  for(size_t i=0;i+4096<=n;i+=4096) if(!memcmp(buf+i,LW_RECORD_MAGIC,16)) {
   struct lw_record r;
   if(!snapshot(pa+i,&r) && !(r.nonce==old_nonce && r.epoch==old_epoch)) {
    printf("{\"event\":\"located\",\"physical\":\"0x%"PRIx64"\",\"nonce\":\"%016"PRIx64"\",\"epoch\":%"PRIu64",\"pid\":%u}\n",pa+i,r.nonce,r.epoch,r.pid);fflush(stdout);
    free(buf);return pa+i;
   }
  }
 }
 free(buf);return 0;
}
static void guards(void) {
 unsigned char b[16];int result;
 errno=0;result=readmem(info.extent[0].base,b,8,info.generation^1);
 if(result!=-1 || errno!=ESTALE) {fputs("stale generation accepted\n",stderr);exit(4);}
 uint64_t bad[]={0,UINT64_MAX-3,info.extent[0].base+info.extent[0].bytes-4,0xfec00000};
 for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++) {
  errno=0;result=readmem(bad[i],b,8,info.generation);
  if(result!=-1 || errno!=ERANGE) {fputs("range guard failed\n",stderr);exit(4);}
 }
 int writable=open("/dev/lwobserve",O_RDWR);
 if(writable!=-1 || errno!=EPERM) {fputs("write open accepted\n",stderr);exit(4);}
 puts("{\"event\":\"guards\",\"stale_generation\":true,\"out_of_range\":true,\"write_denied\":true}");
}
int main(int argc,char **argv) {
 double seconds=argc>1?strtod(argv[1],NULL):40;
 fd=open("/dev/lwobserve",O_RDONLY);if(fd<0){perror("open");return 2;}
 if(ioctl(fd,LWOBS_INFO,&info) || info.version!=1 || info.count!=3) return 2;
 guards();
 uint64_t pa=0;double deadline=now(CLOCK_MONOTONIC)+60;
 while(!pa && now(CLOCK_MONOTONIC)<deadline) pa=locate(0,0);
 if(!pa){fputs("live writer not found\n",stderr);return 5;}
 struct lw_record r;while(snapshot(pa,&r)) {}
 uint64_t nonce=r.nonce,epoch=r.epoch;epochs=1;
 double start=now(CLOCK_MONOTONIC),cpu=now(CLOCK_PROCESS_CPUTIME_ID);
 while(attempts<1000000 || now(CLOCK_MONOTONIC)-start<seconds) {
  double before=now(CLOCK_MONOTONIC);int state=snapshot(pa,&r);
  uint64_t ns=(uint64_t)((now(CLOCK_MONOTONIC)-before)*1e9),bucket=0;
  while(ns>1 && bucket<63){ns>>=1;bucket++;}hist[bucket]++;attempts++;
  if(!state && (r.nonce!=nonce || r.epoch!=epoch)) state=4;
  switch(state) {
   case 0: accepted++;if(r.sequence<seq_min)seq_min=r.sequence;if(r.sequence>seq_max)seq_max=r.sequence;break;
   case 1:busy++;break;case 2:torn++;break;case 4:invalid++;break;case 5:wrong++;break;
   case 3:
    revoked++;pa=0;
    /* Tombstoned identity is retired permanently; no further payload reads. */
    deadline=now(CLOCK_MONOTONIC)+15;
    while(!pa && now(CLOCK_MONOTONIC)<deadline) {
     struct timespec delay={0,100000000};nanosleep(&delay,NULL);pa=locate(nonce,epoch);
    }
    if(!pa){fputs("replacement buffer absent\n",stderr);return 6;}
    while(snapshot(pa,&r)){} nonce=r.nonce;epoch=r.epoch;epochs++;break;
  }
 }
 double wall=now(CLOCK_MONOTONIC)-start;cpu=now(CLOCK_PROCESS_CPUTIME_ID)-cpu;
 int pass=accepted>0 && wrong==0 && busy>0 && revoked>0 && epochs>=2;
 printf("{\"event\":\"result\",\"passed\":%s,\"generation\":%"PRIu64",\"attempts\":%"PRIu64",\"accepted\":%"PRIu64",\"busy\":%"PRIu64",\"torn\":%"PRIu64",\"revoked\":%"PRIu64",\"invalid\":%"PRIu64",\"bad_payload\":%"PRIu64",\"epochs\":%"PRIu64",\"seconds\":%.6f,\"cpu_seconds\":%.6f,\"accepted_mib_per_second\":%.6f,\"latency_log2_ns\":[",pass?"true":"false",(uint64_t)info.generation,attempts,accepted,busy,torn,revoked,invalid,wrong,epochs,wall,cpu,accepted*4096.0/(1024*1024*wall));
 for(unsigned i=0;i<64;i++) { printf("%s%"PRIu64,i?",":"",hist[i]); }
 puts("]}");
 return pass?0:7;
}
