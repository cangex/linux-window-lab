// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <Uefi.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DevicePath.h>
#include <Guid/Acpi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/DebugLib.h>
#include <LwLab.h>
STATIC EFI_BLOCK_IO_MEDIA mMedia={1,FALSE,TRUE,FALSE,TRUE,FALSE,512,1,(LW_DISK_SIZE/512)-1};
STATIC EFI_STATUS EFIAPI Reset(EFI_BLOCK_IO_PROTOCOL *This, BOOLEAN Verify) { return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI Read(EFI_BLOCK_IO_PROTOCOL *This, UINT32 Id, EFI_LBA Lba, UINTN Size, VOID *Buffer) {
 if (Id!=mMedia.MediaId) return EFI_MEDIA_CHANGED;
 if (!Size) return EFI_SUCCESS;
 if (!Buffer) return EFI_INVALID_PARAMETER;
 if (Size%512) return EFI_BAD_BUFFER_SIZE;
 if (Lba>mMedia.LastBlock || Size/512>mMedia.LastBlock-Lba+1) return EFI_INVALID_PARAMETER;
 CopyMem(Buffer,(VOID *)(UINTN)(LW_DISK+Lba*512),Size); return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI Write(EFI_BLOCK_IO_PROTOCOL *This, UINT32 Id, EFI_LBA Lba, UINTN Size, VOID *Buffer) { return EFI_WRITE_PROTECTED; }
STATIC EFI_STATUS EFIAPI Flush(EFI_BLOCK_IO_PROTOCOL *This) { return EFI_SUCCESS; }
STATIC EFI_BLOCK_IO_PROTOCOL mBlock={EFI_BLOCK_IO_PROTOCOL_REVISION,&mMedia,Reset,Read,Write,Flush};
#pragma pack(1)
STATIC struct { VENDOR_DEVICE_PATH Vendor; EFI_DEVICE_PATH_PROTOCOL End; } mPath={
 {{HARDWARE_DEVICE_PATH,HW_VENDOR_DP,{sizeof(VENDOR_DEVICE_PATH),0}},{0x9754051f,0xe7e4,0x4509,{0xae,0x38,0x61,0x7d,0x65,0x9d,0x36,0x90}}},
 {END_DEVICE_PATH_TYPE,END_ENTIRE_DEVICE_PATH_SUBTYPE,{4,0}}};
#pragma pack()
EFI_STATUS EFIAPI LwPlatformEntry(EFI_HANDLE Image, EFI_SYSTEM_TABLE *System) {
 EFI_HANDLE Disk=NULL; EFI_STATUS Status;
 LW_MBOX->Phase=3; LW_MBOX->Rsdp=LW_ACPI;
 Status=gBS->InstallConfigurationTable(&gEfiAcpi20TableGuid,(VOID *)(UINTN)LW_ACPI);
 if (EFI_ERROR(Status)) LwFail(0x301,Status);
 Status=gBS->InstallMultipleProtocolInterfaces(&Disk,&gEfiDevicePathProtocolGuid,&mPath,&gEfiBlockIoProtocolGuid,&mBlock,NULL);
 DEBUG((DEBUG_INFO,"LWLAB RAM disk installed %r, ACPI=%lx\n",Status,LW_ACPI));
 return Status;
}
