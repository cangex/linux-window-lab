// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <Uefi.h>
#include <Protocol/Cpu.h>
#include <Protocol/Timer.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/CpuExceptionHandlerLib.h>
#include <Library/IoLib.h>
#include <Library/TimerLib.h>
#include <Library/DebugLib.h>
#include <Library/NestedInterruptTplLib.h>
#include <LwLab.h>
STATIC BOOLEAN mX2;
STATIC UINT64 mLapicHz, mPeriod;
STATIC EFI_TIMER_NOTIFY mNotify;
STATIC UINT32 ApicRead(UINTN Reg) { return mX2 ? (UINT32)AsmReadMsr64(0x800+(Reg>>4)) : MmioRead32(LW_LAPIC+Reg); }
STATIC VOID ApicWrite(UINTN Reg, UINT32 V) { if (mX2) AsmWriteMsr64(0x800+(Reg>>4),V); else MmioWrite32(LW_LAPIC+Reg,V); }
STATIC EFI_STATUS EFIAPI Flush(EFI_CPU_ARCH_PROTOCOL *This, EFI_PHYSICAL_ADDRESS A, UINT64 L, EFI_CPU_FLUSH_TYPE T) {
 if (T != EfiCpuFlushTypeWriteBackInvalidate) return EFI_UNSUPPORTED;
 AsmWbinvd(); return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI Enable(EFI_CPU_ARCH_PROTOCOL *This) { EnableInterrupts(); return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI Disable(EFI_CPU_ARCH_PROTOCOL *This) { DisableInterrupts(); return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI GetState(EFI_CPU_ARCH_PROTOCOL *This, BOOLEAN *State) { if (!State) return EFI_INVALID_PARAMETER; *State=GetInterruptState(); return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI Init(EFI_CPU_ARCH_PROTOCOL *This, EFI_CPU_INIT_TYPE Type) { return EFI_UNSUPPORTED; }
STATIC EFI_STATUS EFIAPI Register(EFI_CPU_ARCH_PROTOCOL *This, EFI_EXCEPTION_TYPE Type, EFI_CPU_INTERRUPT_HANDLER Handler) { return RegisterCpuInterruptHandler(Type,Handler); }
STATIC EFI_STATUS EFIAPI GetTimer(EFI_CPU_ARCH_PROTOCOL *This, UINT32 Index, UINT64 *Value, UINT64 *Period) {
 if (Index || !Value) return EFI_INVALID_PARAMETER;
 *Value=AsmReadTsc(); if (Period) *Period=DivU64x64Remainder(1000000000000000ULL,LW_HAND->TscHz,NULL); return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI Attributes(EFI_CPU_ARCH_PROTOCOL *This, EFI_PHYSICAL_ADDRESS Base, UINT64 Length, UINT64 Attr) {
 if (!Length || (Base & 4095) || (Length & 4095)) return EFI_INVALID_PARAMETER;
 if (Base<LW_BASE || Base>=LW_END || Length>LW_END-Base) return EFI_UNSUPPORTED;
 // The static page tables already provide writable/executable WB memory.
 return (Attr==0 || Attr==EFI_MEMORY_WB) ? EFI_SUCCESS : EFI_UNSUPPORTED;
}
STATIC EFI_CPU_ARCH_PROTOCOL mCpu={Flush,Enable,Disable,GetState,Init,Register,GetTimer,Attributes,1,64};
STATIC VOID EFIAPI TimerInterrupt(EFI_EXCEPTION_TYPE Type, EFI_SYSTEM_CONTEXT Context) {
 STATIC NESTED_INTERRUPT_STATE Nested;
 EFI_TPL Old=NestedInterruptRaiseTPL();
 ApicWrite(0xb0,0);
 LW_MBOX->TimerTicks++;
 if (mNotify) mNotify(mPeriod);
 NestedInterruptRestoreTPL(Old,Context,&Nested);
}
// No external interrupt source is assigned to this partition.
STATIC VOID EFIAPI UnexpectedInterrupt(EFI_EXCEPTION_TYPE Type, EFI_SYSTEM_CONTEXT Context) {
 LwFail(0x280+Type,Type);
}
STATIC EFI_STATUS EFIAPI Notify(EFI_TIMER_ARCH_PROTOCOL *This, EFI_TIMER_NOTIFY Function) {
 if (Function && mNotify) return EFI_ALREADY_STARTED;
 if (!Function && !mNotify) return EFI_INVALID_PARAMETER;
 mNotify=Function; return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI SetPeriod(EFI_TIMER_ARCH_PROTOCOL *This, UINT64 Period) {
 UINT64 Count;
 if (!Period) { ApicWrite(0x320,0x10040); mPeriod=0; ApicWrite(0x380,0); return EFI_SUCCESS; }
 if (Period>DivU64x64Remainder(MAX_UINT64,mLapicHz,NULL)) return EFI_UNSUPPORTED;
 Count=DivU64x64Remainder(MultU64x64(Period,mLapicHz),10000000,NULL);
 if (!Count || Count>MAX_UINT32) return EFI_UNSUPPORTED;
 ApicWrite(0x320,0x10040); mPeriod=Period; ApicWrite(0x3e0,3); ApicWrite(0x320,0x20040); ApicWrite(0x380,(UINT32)Count);
 return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI GetPeriod(EFI_TIMER_ARCH_PROTOCOL *This, UINT64 *Period) { if (!Period) return EFI_INVALID_PARAMETER; *Period=mPeriod; return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI Soft(EFI_TIMER_ARCH_PROTOCOL *This) { return EFI_UNSUPPORTED; }
STATIC EFI_TIMER_ARCH_PROTOCOL mTimer={Notify,SetPeriod,GetPeriod,Soft};
EFI_STATUS EFIAPI LwCpuEntry(EFI_HANDLE Image, EFI_SYSTEM_TABLE *System) {
 EFI_STATUS Status; EFI_HANDLE Handle=NULL; UINTN Vector; UINT64 Base=AsmReadMsr64(0x1b);
 LW_MBOX->Phase=2;
 if (!(Base & BIT11) || (Base & 0xfffff000)!=LW_LAPIC) LwFail(0x201,Base);
 mX2=(Base & BIT10)!=0;
 Status=InitializeCpuExceptionHandlers(NULL); if (EFI_ERROR(Status)) LwFail(0x202,Status);
 for (Vector=32;Vector<255;Vector++) if (Vector!=0x40) {
  Status=RegisterCpuInterruptHandler(Vector,UnexpectedInterrupt);
  if (EFI_ERROR(Status)) LwFail(0x207,Status);
 }
 Status=RegisterCpuInterruptHandler(0x40,TimerInterrupt); if (EFI_ERROR(Status)) LwFail(0x203,Status);
 ApicWrite(0xf0,0x1ff); ApicWrite(0x350,0x10000); ApicWrite(0x360,0x10000); ApicWrite(0x370,0x10000);
 ApicWrite(0x320,0x10040); ApicWrite(0x3e0,3); ApicWrite(0x380,MAX_UINT32);
 MicroSecondDelay(10000); mLapicHz=(MAX_UINT32-ApicRead(0x390))*100ULL; ApicWrite(0x380,0);
 if (!mLapicHz) LwFail(0x204,1);
 Status=gBS->InstallMultipleProtocolInterfaces(&Handle,&gEfiCpuArchProtocolGuid,&mCpu,&gEfiTimerArchProtocolGuid,&mTimer,NULL);
 if (EFI_ERROR(Status)) LwFail(0x205,Status);
 Status=SetPeriod(&mTimer,100000); if (EFI_ERROR(Status)) LwFail(0x206,Status);
 DEBUG((DEBUG_INFO,"LWLAB CPU APIC=%u LAPIC Hz=%Lu\n",LW_MBOX->Apic,mLapicHz));
 return EFI_SUCCESS;
}
