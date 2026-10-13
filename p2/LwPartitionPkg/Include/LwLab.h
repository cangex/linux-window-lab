// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/CpuLib.h>
#include "Platform.h"
#define LW_MAGIC 0x313030765041574cULL
#define LW_CHECK_ALL 0x1ffULL
#define LW_MBOX ((volatile LW_MAILBOX *)(UINTN)(LW_BASE+0x1000))
#define LW_HAND ((volatile LW_HANDOFF *)(UINTN)LW_BASE)
typedef struct {
  UINT64 Magic; UINT32 Version, Size; UINT64 Generation;
  UINT32 Cpu, Apic; UINT64 Base, Bytes, Entry, Stack, Cr3, Mailbox, Flags, TscHz;
} LW_HANDOFF;
typedef struct {
  UINT64 Generation; UINT32 Apic, Stage;
  UINT64 Heartbeat, Tsc, Error, Cr3, Stack, Magic;
  UINT64 Checks, FailedCase, TimerTicks, Phase, SystemTable, Rsdp, AllocLow, AllocHigh;
} LW_MAILBOX;
STATIC inline VOID LwFail(UINT64 Case, UINT64 Status) {
  DisableInterrupts();
  LW_MBOX->FailedCase=Case; LW_MBOX->Error=Status ? Status : 1;
  MemoryFence(); LW_MBOX->Stage=255;
  for (;;) CpuSleep();
}
