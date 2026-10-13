/* SPDX-License-Identifier: MIT */
#ifndef LW_RECORD_H
#define LW_RECORD_H
#include <stdint.h>
#define LW_RECORD_MAGIC "LWLAB-P4-RECORD1"
#define LW_PAYLOAD_BYTES 4016
struct lw_record {
 char magic[16]; uint32_t version, length; uint64_t nonce, sequence, epoch;
 uint32_t state, bytes, pid, reserved; uint64_t checksum;
 unsigned char payload[LW_PAYLOAD_BYTES]; uint64_t tail;
};
_Static_assert(sizeof(struct lw_record)==4096,"record ABI");
static uint64_t lw_mix(uint64_t x) {
 x^=x>>30; x*=UINT64_C(0xbf58476d1ce4e5b9); x^=x>>27;
 x*=UINT64_C(0x94d049bb133111eb); return x^(x>>31);
}
static uint64_t lw_word(uint64_t nonce,uint64_t epoch,uint64_t seq,unsigned i) {
 return lw_mix(nonce ^ (epoch*UINT64_C(0x9e3779b97f4a7c15)) ^ seq ^ ((uint64_t)i<<32));
}
static uint64_t lw_hash(const unsigned char *p,unsigned bytes) {
 uint64_t h=UINT64_C(14695981039346656037);
 for(unsigned i=0;i<bytes;i++) { h^=p[i];h*=UINT64_C(1099511628211); }
 return h;
}
#endif
