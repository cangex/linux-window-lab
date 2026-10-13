/* SPDX-License-Identifier: MIT */
#define main benchmark_main
#include "../reader.c"
#undef main
#include <assert.h>
int main(void) {
 struct lw_record r={0};memcpy(r.magic,LW_RECORD_MAGIC,16);
 r.version=1;r.length=4096;r.nonce=123;r.sequence=r.tail=8;r.epoch=1;
 r.state=1;r.bytes=LW_PAYLOAD_BYTES;r.pid=999;
 for(unsigned i=0;i<LW_PAYLOAD_BYTES/8;i++) {uint64_t v=lw_word(123,1,8,i);memcpy(r.payload+i*8,&v,8);}
 r.checksum=lw_hash(r.payload,LW_PAYLOAD_BYTES);
 assert(check(&r,8,8)==0);
 assert(check(&r,7,8)==1);assert(check(&r,8,10)==2);
 r.tail=6;assert(check(&r,8,8)==2);r.tail=8;
 r.payload[150]^=1;assert(check(&r,8,8)==5);r.payload[150]^=1;
 r.state=2;assert(check(&r,8,8)==3);r.state=1;
 r.version=9;assert(check(&r,8,8)==4);r.version=1;
 r.epoch=2;assert(check(&r,8,8)==5);
 puts("8 protocol checks passed");return 0;
}
