/* SPDX-License-Identifier: MIT */
#include <stdint.h>
#include <x86intrin.h>
uint64_t lw_tsc(void) { _mm_lfence();uint64_t value=__rdtsc();_mm_lfence();return value; }
