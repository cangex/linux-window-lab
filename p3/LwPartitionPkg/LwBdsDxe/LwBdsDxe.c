// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <Uefi.h>
#include <Guid/EventGroup.h>
#include <Protocol/Bds.h>
#include <Protocol/BlockIo.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/SimpleTextIn.h>
#include <Protocol/SimpleTextOut.h>
#include <Protocol/LoadedImage.h>
#include <Library/UefiLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/DebugLib.h>
#include <Library/SerialPortLib.h>
#include <Library/BaseMemoryLib.h>
#include <LwLab.h>
#include "RamGop.h"

STATIC EFI_HANDLE mImage;
STATIC struct { VENDOR_DEVICE_PATH Vendor; EFI_DEVICE_PATH_PROTOCOL End; } mConsolePath = {
 {{HARDWARE_DEVICE_PATH,HW_VENDOR_DP,{sizeof(VENDOR_DEVICE_PATH),0}},
  {0x58bf1182,0x0d4e,0x42d4,{0xab,0x18,0x97,0x51,0x72,0x50,0x03,0x01}}},
 {END_DEVICE_PATH_TYPE,END_ENTIRE_DEVICE_PATH_SUBTYPE,{sizeof(EFI_DEVICE_PATH_PROTOCOL),0}}
};
STATIC EFI_EXIT_BOOT_SERVICES mExit;
STATIC EFI_LOCATE_PROTOCOL mLocate;
STATIC EFI_LOCATE_HANDLE mLocateHandle;
STATIC EFI_OPEN_PROTOCOL mOpen;
STATIC EFI_ALLOCATE_PAGES mAllocate;
STATIC EFI_GET_TIME mGetTime;
STATIC EFI_STATUS EFIAPI LocateTrace(EFI_GUID *Protocol, VOID *Registration, VOID **Interface) {
 EFI_STATUS S=mLocate(Protocol,Registration,Interface);
 DEBUG((DEBUG_ERROR,"P3 LocateProtocol %g -> %r\n",Protocol,S)); return S;
}
STATIC EFI_STATUS EFIAPI HandleTrace(EFI_LOCATE_SEARCH_TYPE Type, EFI_GUID *Protocol, VOID *Key, UINTN *Size, EFI_HANDLE *Buffer) {
 EFI_STATUS S=mLocateHandle(Type,Protocol,Key,Size,Buffer);
 if (Protocol) { DEBUG((DEBUG_ERROR,"P3 LocateHandle %g -> %r\n",Protocol,S)); } return S;
}
STATIC EFI_STATUS EFIAPI OpenTrace(EFI_HANDLE Handle, EFI_GUID *Protocol, VOID **Interface, EFI_HANDLE Agent, EFI_HANDLE Controller, UINT32 Attr) {
 EFI_STATUS S=mOpen(Handle,Protocol,Interface,Agent,Controller,Attr);
 if (EFI_ERROR(S)) { DEBUG((DEBUG_ERROR,"P3 OpenProtocol %g -> %r\n",Protocol,S)); } return S;
}
STATIC EFI_STATUS EFIAPI AllocateTrace(EFI_ALLOCATE_TYPE Type, EFI_MEMORY_TYPE Kind, UINTN Pages, EFI_PHYSICAL_ADDRESS *Address) {
 EFI_PHYSICAL_ADDRESS Requested=Address ? *Address : 0;
 EFI_STATUS S=mAllocate(Type,Kind,Pages,Address);
 if (EFI_ERROR(S)) { DEBUG((DEBUG_ERROR,"P3 AllocatePages type=%u kind=%u pages=%lu address=%lx -> %r\n",Type,Kind,Pages,Requested,S)); } return S;
}
STATIC EFI_STATUS EFIAPI TimeTrace(EFI_TIME *Time, EFI_TIME_CAPABILITIES *Capabilities) {
 STATIC UINTN Calls;
 EFI_STATUS S=mGetTime(Time,Capabilities);
 if (++Calls<=3 || EFI_ERROR(S)) DEBUG((DEBUG_ERROR,"P3 GetTime -> %r\n",S));
 return S;
}
STATIC EFI_SIMPLE_TEXT_OUTPUT_MODE mMode={1,0,7,0,0,TRUE};
STATIC EFI_STATUS EFIAPI TextReset(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, BOOLEAN Extended) { return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI TextWrite(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, CHAR16 *Text) {
 if (!Text) return EFI_INVALID_PARAMETER;
 while (*Text) { UINT8 Ch=(*Text <= 0x7f) ? (UINT8)*Text : '?'; SerialPortWrite(&Ch,1); Text++; }
 return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI TextTest(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, CHAR16 *Text) {
 if (!Text) return EFI_INVALID_PARAMETER;
 while (*Text) if (*Text++ > 0x7f) return EFI_UNSUPPORTED;
 return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI TextQuery(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, UINTN Mode, UINTN *Columns, UINTN *Rows) {
 if (!Columns || !Rows) return EFI_INVALID_PARAMETER;
 if (Mode) return EFI_UNSUPPORTED;
 *Columns=80; *Rows=25; return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI TextMode(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, UINTN Mode) { return Mode ? EFI_UNSUPPORTED : EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI TextAttr(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, UINTN Attr) {
 if (Attr & ~0x7fU) return EFI_UNSUPPORTED;
 mMode.Attribute=(INT32)Attr; return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI TextClear(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This) { mMode.CursorColumn=0; mMode.CursorRow=0; return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI TextCursor(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, UINTN Col, UINTN Row) {
 if (Col>=80 || Row>=25) return EFI_UNSUPPORTED;
 mMode.CursorColumn=(INT32)Col; mMode.CursorRow=(INT32)Row; return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI TextEnable(EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *This, BOOLEAN Enabled) { mMode.CursorVisible=Enabled; return EFI_SUCCESS; }
STATIC EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL mOut={TextReset,TextWrite,TextTest,TextQuery,TextMode,TextAttr,TextClear,TextCursor,TextEnable,&mMode};
STATIC EFI_STATUS EFIAPI InputReset(EFI_SIMPLE_TEXT_INPUT_PROTOCOL *This, BOOLEAN Extended) { return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI InputRead(EFI_SIMPLE_TEXT_INPUT_PROTOCOL *This, EFI_INPUT_KEY *Key) {
 UINT8 Ch;
 if (!Key) return EFI_INVALID_PARAMETER;
 if (!SerialPortPoll()) return EFI_NOT_READY;
 if (SerialPortRead(&Ch,1)!=1) return EFI_NOT_READY;
 Key->ScanCode=0; Key->UnicodeChar=Ch; return EFI_SUCCESS;
}
STATIC VOID EFIAPI InputNotify(EFI_EVENT Event, VOID *Context) { if (SerialPortPoll()) gBS->SignalEvent(Event); }
STATIC EFI_SIMPLE_TEXT_INPUT_PROTOCOL mIn={InputReset,InputRead,NULL};

STATIC EFI_STATUS EFIAPI ExitTrace(EFI_HANDLE Image, UINTN Key) {
 EFI_STATUS Status;
 DEBUG((DEBUG_ERROR,"LWLAB P3 ExitBootServices request key=%lx\n",Key));
 gST->RuntimeServices->GetTime=mGetTime;
 gST->RuntimeServices->Hdr.CRC32=0;
 gBS->CalculateCrc32(gST->RuntimeServices,gST->RuntimeServices->Hdr.HeaderSize,&gST->RuntimeServices->Hdr.CRC32);
 Status=mExit(Image,Key);
 // SerialPortLib is fixed COM2 and needs no Boot Services after successful exit.
 DEBUG((DEBUG_ERROR,"LWLAB P3 ExitBootServices returned %r\n",Status));
 if (!EFI_ERROR(Status)) { LW_MBOX->Phase=21; MemoryFence(); LW_MBOX->Stage=3; }
 return Status;
}
STATIC VOID EFIAPI Bds(EFI_BDS_ARCH_PROTOCOL *This) {
 EFI_STATUS Status; EFI_HANDLE *Handles, App, Console=NULL; UINTN Count, I;
 EFI_DEVICE_PATH_PROTOCOL *Path; EFI_LOADED_IMAGE_PROTOCOL *Loaded;
 Status=gBS->CreateEvent(EVT_NOTIFY_WAIT,TPL_NOTIFY,InputNotify,NULL,&mIn.WaitForKey);
 if (EFI_ERROR(Status)) LwFail(0x410,Status);
 Status=gBS->InstallMultipleProtocolInterfaces(&Console,&gEfiSimpleTextOutProtocolGuid,&mOut,&gEfiSimpleTextInProtocolGuid,&mIn,&gEfiGraphicsOutputProtocolGuid,&mGop,&gEfiDevicePathProtocolGuid,&mConsolePath,NULL);
 if (EFI_ERROR(Status)) LwFail(0x411,Status);
 GopSet(&mGop,0);
 DEBUG((DEBUG_ERROR,"LWLAB P3 RAM GOP base=%lx bytes=%u 1024x768 BGRX\n",(UINT64)FB_ADDRESS,(UINT32)FB_BYTES));
 gST->ConsoleInHandle=Console; gST->ConIn=&mIn;
 gST->ConsoleOutHandle=Console; gST->ConOut=&mOut;
 gST->StandardErrorHandle=Console; gST->StdErr=&mOut;
 gST->Hdr.CRC32=0; gBS->CalculateCrc32(gST,gST->Hdr.HeaderSize,&gST->Hdr.CRC32);
 mExit=gBS->ExitBootServices; gBS->ExitBootServices=ExitTrace;
 mLocate=gBS->LocateProtocol; gBS->LocateProtocol=LocateTrace;
 mLocateHandle=gBS->LocateHandle; gBS->LocateHandle=HandleTrace;
 mOpen=gBS->OpenProtocol; gBS->OpenProtocol=OpenTrace;
 mAllocate=gBS->AllocatePages; gBS->AllocatePages=AllocateTrace;
 mGetTime=gST->RuntimeServices->GetTime; gST->RuntimeServices->GetTime=TimeTrace;
 gST->RuntimeServices->Hdr.CRC32=0;
 gBS->CalculateCrc32(gST->RuntimeServices,gST->RuntimeServices->Hdr.HeaderSize,&gST->RuntimeServices->Hdr.CRC32);
 gBS->Hdr.CRC32=0; gBS->CalculateCrc32(gBS,gBS->Hdr.HeaderSize,&gBS->Hdr.CRC32);
 EfiEventGroupSignal(&gEfiEndOfDxeEventGroupGuid);
 LW_MBOX->Phase=10; LW_MBOX->SystemTable=(UINTN)gST;
 Status=gBS->LocateHandleBuffer(ByProtocol,&gEfiBlockIoProtocolGuid,NULL,&Count,&Handles);
 if (EFI_ERROR(Status) || Count!=1) LwFail(0x401,Status);
 for (I=0;I<Count;I++) gBS->ConnectController(Handles[I],NULL,NULL,TRUE);
 FreePool(Handles);
 Status=gBS->LocateHandleBuffer(ByProtocol,&gEfiSimpleFileSystemProtocolGuid,NULL,&Count,&Handles);
 if (EFI_ERROR(Status) || Count!=1) LwFail(0x402,Status);
 Path=FileDevicePath(Handles[0],L"\\EFI\\Microsoft\\Boot\\bootmgfw.efi"); FreePool(Handles);
 Status=gBS->LoadImage(FALSE,mImage,Path,NULL,0,&App); FreePool(Path);
 DEBUG((DEBUG_ERROR,"LWLAB P3 bootmgfw LoadImage: %r\n",Status));
 if (EFI_ERROR(Status)) LwFail(0x403,Status);
 Status=gBS->HandleProtocol(App,&gEfiLoadedImageProtocolGuid,(VOID **)&Loaded);
 if (EFI_ERROR(Status)) LwFail(0x412,Status);
 DEBUG((DEBUG_ERROR,"LWLAB P3 bootmgfw image=%p size=%lx\n",Loaded->ImageBase,Loaded->ImageSize));
 EfiSignalEventReadyToBoot();
 // This handshake means firmware readiness only, never Windows userspace.
 LW_MBOX->Phase=11; MemoryFence(); LW_MBOX->Stage=2;
 DEBUG((DEBUG_ERROR,"LWLAB P3 bootmgfw StartImage generation=%lu\n",LW_MBOX->Generation));
 Status=gBS->StartImage(App,NULL,NULL);
 DEBUG((DEBUG_ERROR,"LWLAB P3 bootmgfw returned: %r\n",Status));
 LwFail(0x404,Status);
}
STATIC EFI_BDS_ARCH_PROTOCOL mBds={Bds};
EFI_STATUS EFIAPI LwBdsEntry(EFI_HANDLE Image, EFI_SYSTEM_TABLE *System) {
 EFI_HANDLE Handle=NULL; mImage=Image;
 return gBS->InstallMultipleProtocolInterfaces(&Handle,&gEfiBdsArchProtocolGuid,&mBds,NULL);
}
