// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <Uefi.h>
#include <Protocol/Reset.h>
#include <Protocol/RealTimeClock.h>
#include <Guid/EventGroup.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/UefiRuntimeLib.h>
#include <LwLab.h>
STATIC volatile LW_MAILBOX *mMailbox=LW_MBOX;
STATIC UINT64 mEpoch, mOrigin, mHz;
STATIC VOID EFIAPI VirtualChange(EFI_EVENT Event, VOID *Context) { EfiConvertPointer(0,(VOID **)&mMailbox); }
STATIC VOID EFIAPI Reset(EFI_RESET_TYPE Type, EFI_STATUS Status, UINTN Size, VOID *Data) {
 DisableInterrupts(); mMailbox->FailedCase=0x800+Type; mMailbox->Error=EFI_UNSUPPORTED; MemoryFence(); mMailbox->Stage=255;
 for (;;) CpuSleep();
}
STATIC BOOLEAN Leap(UINT64 Year) { return Year%4==0 && (Year%100!=0 || Year%400==0); }
STATIC EFI_STATUS EFIAPI GetTime(EFI_TIME *Time, EFI_TIME_CAPABILITIES *Capabilities) {
 STATIC CONST UINT8 Months[12]={31,28,31,30,31,30,31,31,30,31,30,31};
 UINT64 Seconds, Days, Year=1970, Month=0, Length;
 if (!Time) return EFI_INVALID_PARAMETER;
 if (!mHz) return EFI_DEVICE_ERROR;
 Seconds=mEpoch+(AsmReadTsc()-mOrigin)/mHz; Days=Seconds/86400;
 while (Year<=9999) { Length=Leap(Year)?366:365; if (Days<Length) break; Days-=Length; Year++; }
 if (Year>9999) return EFI_DEVICE_ERROR;
 while (Month<11) { Length=Months[Month]+(Month==1 && Leap(Year)); if (Days<Length) break; Days-=Length; Month++; }
 *Time=(EFI_TIME){(UINT16)Year,(UINT8)(Month+1),(UINT8)(Days+1),
   (UINT8)(Seconds/3600%24),(UINT8)(Seconds/60%60),(UINT8)(Seconds%60),0,0,0,0,0};
 if (Capabilities) *Capabilities=(EFI_TIME_CAPABILITIES){1,50000000,FALSE};
 return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI SetTime(EFI_TIME *Time) { return Time ? EFI_UNSUPPORTED : EFI_INVALID_PARAMETER; }
STATIC EFI_STATUS EFIAPI GetWake(BOOLEAN *Enabled, BOOLEAN *Pending, EFI_TIME *Time) { return EFI_UNSUPPORTED; }
STATIC EFI_STATUS EFIAPI SetWake(BOOLEAN Enable, EFI_TIME *Time) { return EFI_UNSUPPORTED; }
EFI_STATUS EFIAPI LwRuntimeEntry(EFI_HANDLE Image, EFI_SYSTEM_TABLE *System) {
 EFI_HANDLE Handle=NULL; EFI_EVENT Event; EFI_STATUS Status;
 // ABI 3 supplies Linux UTC seconds in the former Flags slot. No shared RTC I/O.
 mEpoch=LW_HAND->Flags; mHz=LW_HAND->TscHz; mOrigin=AsmReadTsc();
 Status=gBS->CreateEventEx(EVT_NOTIFY_SIGNAL,TPL_NOTIFY,VirtualChange,NULL,&gEfiEventVirtualAddressChangeGuid,&Event);
 if (EFI_ERROR(Status)) return Status;
 gRT->ResetSystem=Reset; gRT->GetTime=GetTime; gRT->SetTime=SetTime; gRT->GetWakeupTime=GetWake; gRT->SetWakeupTime=SetWake;
 return gBS->InstallMultipleProtocolInterfaces(&Handle,&gEfiResetArchProtocolGuid,NULL,&gEfiRealTimeClockArchProtocolGuid,NULL,NULL);
}
