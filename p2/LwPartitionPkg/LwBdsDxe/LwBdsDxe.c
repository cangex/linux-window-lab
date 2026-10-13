// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <Uefi.h>
#include <Guid/EventGroup.h>
#include <Library/UefiLib.h>
#include <Protocol/Bds.h>
#include <Protocol/BlockIo.h>
#include <Protocol/SimpleFileSystem.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/DebugLib.h>
#include <LwLab.h>
STATIC EFI_HANDLE mImage;
STATIC VOID EFIAPI Bds(EFI_BDS_ARCH_PROTOCOL *This) {
 EFI_STATUS Status; EFI_HANDLE *Handles, App; UINTN Count, I; EFI_DEVICE_PATH_PROTOCOL *Path;
 EfiEventGroupSignal(&gEfiEndOfDxeEventGroupGuid);
 LW_MBOX->Phase=4; LW_MBOX->SystemTable=(UINTN)gST;
 Status=gBS->LocateHandleBuffer(ByProtocol,&gEfiBlockIoProtocolGuid,NULL,&Count,&Handles);
 if (EFI_ERROR(Status) || Count!=1) LwFail(0x401,Status);
 for (I=0;I<Count;I++) { Status=gBS->ConnectController(Handles[I],NULL,NULL,TRUE); DEBUG((DEBUG_INFO,"LWLAB connect RAM disk: %r\n",Status)); }
 FreePool(Handles);
 Status=gBS->LocateHandleBuffer(ByProtocol,&gEfiSimpleFileSystemProtocolGuid,NULL,&Count,&Handles);
 if (EFI_ERROR(Status) || Count!=1) LwFail(0x402,Status);
 Path=FileDevicePath(Handles[0],L"\\P2TEST.EFI"); FreePool(Handles);
 Status=gBS->LoadImage(FALSE,mImage,Path,NULL,0,&App); FreePool(Path);
 if (EFI_ERROR(Status)) LwFail(0x403,Status);
 EfiSignalEventReadyToBoot();
 Status=gBS->StartImage(App,NULL,NULL);
 LwFail(0x404,Status);
}
STATIC EFI_BDS_ARCH_PROTOCOL mBds={Bds};
EFI_STATUS EFIAPI LwBdsEntry(EFI_HANDLE Image, EFI_SYSTEM_TABLE *System) {
 EFI_HANDLE Handle=NULL;
 mImage=Image;
 return gBS->InstallMultipleProtocolInterfaces(&Handle,&gEfiBdsArchProtocolGuid,&mBds,NULL);
}
