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
STATIC VOID EFIAPI VirtualChange(EFI_EVENT Event, VOID *Context) { EfiConvertPointer(0,(VOID **)&mMailbox); }
STATIC VOID EFIAPI Reset(EFI_RESET_TYPE Type, EFI_STATUS Status, UINTN Size, VOID *Data) {
 DisableInterrupts(); mMailbox->FailedCase=0x800+Type; mMailbox->Error=EFI_UNSUPPORTED; MemoryFence(); mMailbox->Stage=255;
 for (;;) CpuSleep();
}
STATIC EFI_STATUS EFIAPI GetTime(EFI_TIME *Time, EFI_TIME_CAPABILITIES *Capabilities) { return Time ? EFI_UNSUPPORTED : EFI_INVALID_PARAMETER; }
STATIC EFI_STATUS EFIAPI SetTime(EFI_TIME *Time) { return Time ? EFI_UNSUPPORTED : EFI_INVALID_PARAMETER; }
STATIC EFI_STATUS EFIAPI GetWake(BOOLEAN *Enabled, BOOLEAN *Pending, EFI_TIME *Time) { return EFI_UNSUPPORTED; }
STATIC EFI_STATUS EFIAPI SetWake(BOOLEAN Enable, EFI_TIME *Time) { return EFI_UNSUPPORTED; }
EFI_STATUS EFIAPI LwRuntimeEntry(EFI_HANDLE Image, EFI_SYSTEM_TABLE *System) {
 EFI_HANDLE Handle=NULL; EFI_EVENT Event; EFI_STATUS Status;
 Status=gBS->CreateEventEx(EVT_NOTIFY_SIGNAL,TPL_NOTIFY,VirtualChange,NULL,&gEfiEventVirtualAddressChangeGuid,&Event);
 if (EFI_ERROR(Status)) return Status;
 gRT->ResetSystem=Reset; gRT->GetTime=GetTime; gRT->SetTime=SetTime; gRT->GetWakeupTime=GetWake; gRT->SetWakeupTime=SetWake;
 return gBS->InstallMultipleProtocolInterfaces(&Handle,&gEfiResetArchProtocolGuid,NULL,&gEfiRealTimeClockArchProtocolGuid,NULL,NULL);
}
