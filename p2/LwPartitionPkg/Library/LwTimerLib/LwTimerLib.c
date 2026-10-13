// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <Base.h>
#include <Library/BaseLib.h>
#include <Library/TimerLib.h>
#include <LwLab.h>
STATIC UINT64 mHz;
RETURN_STATUS EFIAPI LwTimerConstructor(VOID) { mHz=LW_HAND->TscHz; return RETURN_SUCCESS; }
UINTN EFIAPI NanoSecondDelay(UINTN Ns) {
  UINT64 Start=AsmReadTsc(), Ticks=DivU64x32(MultU64x64(mHz,Ns),1000000000);
  while (AsmReadTsc()-Start < Ticks) CpuPause();
  return Ns;
}
UINTN EFIAPI MicroSecondDelay(UINTN Us) { NanoSecondDelay(Us*1000); return Us; }
UINT64 EFIAPI GetPerformanceCounter(VOID) { return AsmReadTsc(); }
UINT64 EFIAPI GetPerformanceCounterProperties(UINT64 *Start, UINT64 *End) {
  if (Start) *Start=0;
  if (End) *End=MAX_UINT64;
  return mHz;
}
UINT64 EFIAPI GetTimeInNanoSecond(UINT64 Ticks) {
  UINT64 Rem, Q=DivU64x64Remainder(Ticks,mHz,&Rem);
  return Q*1000000000+DivU64x64Remainder(Rem*1000000000,mHz,NULL);
}
