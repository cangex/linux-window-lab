// SPDX-License-Identifier: BSD-2-Clause-Patent
// One fixed, exclusively assigned endpoint. No shared CF8/CFC or PCI bus scan.
#include <Uefi.h>
#include <Protocol/PciIo.h>
#include <Protocol/DevicePath.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/IoLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/MemoryAllocationLib.h>
#include <LwLab.h>
#include "P5Platform.h"
STATIC UINT64 mAttributes;
STATIC BOOLEAN Owned(UINT64 A,UINT64 N) {
 return N && ((A>=LW_BASE && A<LW_END && N<=LW_END-A) ||
  (A>=P5_HIGH_BASE && A<P5_HIGH_END && N<=P5_HIGH_END-A) ||
  (A>=0x100000 && A<0x1000000 && N<=0x1000000-A) || (A>=0x50000 && A<0x70000 && N<=0x70000-A));
}
STATIC EFI_STATUS Access(BOOLEAN Write,EFI_PCI_IO_PROTOCOL_WIDTH Width,UINT64 Address,UINT64 Limit,UINTN Count,VOID *Buffer) {
 UINTN Size=(UINTN)1<<(Width&3), StepAddress=Size,StepBuffer=Size,I;UINT64 V;
 if (Width>=EfiPciIoWidthMaximum || !Buffer || (Address&(Size-1))) return EFI_INVALID_PARAMETER;
 if (Width>=EfiPciIoWidthFifoUint8 && Width<=EfiPciIoWidthFifoUint64) StepAddress=0;
 if (Width>=EfiPciIoWidthFillUint8 && Width<=EfiPciIoWidthFillUint64) StepBuffer=0;
 if (Address>Limit || (Count && (Size>Limit-Address || (StepAddress && Count>(Limit-Address)/Size)))) return EFI_INVALID_PARAMETER;
 for(I=0;I<Count;I++,Address+=StepAddress,Buffer=(UINT8*)Buffer+StepBuffer) {
  V=0;
  if(Write) {CopyMem(&V,Buffer,Size);switch(Size) {case 1:MmioWrite8(Address,(UINT8)V);break;case 2:MmioWrite16(Address,(UINT16)V);break;case 4:MmioWrite32(Address,(UINT32)V);break;case 8:MmioWrite64(Address,V);break;}}
  else {switch(Size) {case 1:V=MmioRead8(Address);break;case 2:V=MmioRead16(Address);break;case 4:V=MmioRead32(Address);break;case 8:V=MmioRead64(Address);break;}CopyMem(Buffer,&V,Size);}
 }
 return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI MemRead(EFI_PCI_IO_PROTOCOL *This,EFI_PCI_IO_PROTOCOL_WIDTH W,UINT8 Bar,UINT64 Off,UINTN Count,VOID *Buf) {
 if(Bar || Off>=P5_NVME_SIZE) return EFI_UNSUPPORTED;
 return Access(FALSE,W,P5_NVME_BAR+Off,P5_NVME_BAR+P5_NVME_SIZE,Count,Buf);
}
STATIC EFI_STATUS EFIAPI MemWrite(EFI_PCI_IO_PROTOCOL *This,EFI_PCI_IO_PROTOCOL_WIDTH W,UINT8 Bar,UINT64 Off,UINTN Count,VOID *Buf) {
 if(Bar || Off>=P5_NVME_SIZE) return EFI_UNSUPPORTED;
 return Access(TRUE,W,P5_NVME_BAR+Off,P5_NVME_BAR+P5_NVME_SIZE,Count,Buf);
}
STATIC EFI_STATUS EFIAPI ConfigRead(EFI_PCI_IO_PROTOCOL *This,EFI_PCI_IO_PROTOCOL_WIDTH W,UINT32 Off,UINTN Count,VOID *Buf) {
 if(Off>=4096) return EFI_INVALID_PARAMETER;
 return Access(FALSE,W,P5_NVME_ECAM+Off,P5_NVME_ECAM+4096,Count,Buf);
}
STATIC EFI_STATUS EFIAPI ConfigWrite(EFI_PCI_IO_PROTOCOL *This,EFI_PCI_IO_PROTOCOL_WIDTH W,UINT32 Off,UINTN Count,VOID *Buf) {
 // The stock NVMe driver changes command attributes through Attributes().
 return EFI_UNSUPPORTED;
}
STATIC EFI_STATUS EFIAPI Map(EFI_PCI_IO_PROTOCOL *This,EFI_PCI_IO_PROTOCOL_OPERATION Op,VOID *Host,UINTN *Bytes,EFI_PHYSICAL_ADDRESS *Device,VOID **Mapping) {
 if(Op>=EfiPciIoOperationMaximum || !Bytes || !Device || !Mapping || !Owned((UINTN)Host,*Bytes))return EFI_INVALID_PARAMETER;
 if(!(mAttributes&EFI_PCI_IO_ATTRIBUTE_DUAL_ADDRESS_CYCLE) && Op<=EfiPciIoOperationBusMasterCommonBuffer && ((UINTN)Host>MAX_UINT32 || *Bytes>MAX_UINT32-(UINTN)Host+1))return EFI_UNSUPPORTED;
 *Device=(UINTN)Host;*Mapping=NULL;MemoryFence();return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI Unmap(EFI_PCI_IO_PROTOCOL *This,VOID *Mapping) {MemoryFence();return Mapping?EFI_INVALID_PARAMETER:EFI_SUCCESS;}
STATIC EFI_STATUS EFIAPI Allocate(EFI_PCI_IO_PROTOCOL *This,EFI_ALLOCATE_TYPE Type,EFI_MEMORY_TYPE Memory,UINTN Pages,VOID **Host,UINT64 Attr) {
 EFI_PHYSICAL_ADDRESS A=MAX_UINT32;EFI_STATUS S;
 if(!Host || !Pages || (Memory!=EfiBootServicesData && Memory!=EfiRuntimeServicesData))return EFI_INVALID_PARAMETER;
 if(Attr&EFI_PCI_IO_ATTRIBUTE_DUAL_ADDRESS_CYCLE)A=MAX_UINT64;
 S=gBS->AllocatePages(AllocateMaxAddress,Memory,Pages,&A);
 if(!EFI_ERROR(S)) {if(!Owned(A,EFI_PAGES_TO_SIZE(Pages))){gBS->FreePages(A,Pages);return EFI_DEVICE_ERROR;}*Host=(VOID*)(UINTN)A;}
 return S;
}
STATIC EFI_STATUS EFIAPI Free(EFI_PCI_IO_PROTOCOL *This,UINTN Pages,VOID *Host) {return Owned((UINTN)Host,EFI_PAGES_TO_SIZE(Pages))?gBS->FreePages((UINTN)Host,Pages):EFI_INVALID_PARAMETER;}
STATIC EFI_STATUS EFIAPI Flush(EFI_PCI_IO_PROTOCOL *This) {MemoryFence();return EFI_SUCCESS;}
STATIC EFI_STATUS EFIAPI Location(EFI_PCI_IO_PROTOCOL *This,UINTN *Seg,UINTN *Bus,UINTN *Dev,UINTN *Fun) {
 if(!Seg||!Bus||!Dev||!Fun)return EFI_INVALID_PARAMETER;
 *Seg=0;*Bus=129;*Dev=0;*Fun=0;return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI Attributes(EFI_PCI_IO_PROTOCOL *This,EFI_PCI_IO_PROTOCOL_ATTRIBUTE_OPERATION Op,UINT64 Attr,UINT64 *Result) {
 UINT64 Supported=EFI_PCI_IO_ATTRIBUTE_MEMORY|EFI_PCI_IO_ATTRIBUTE_BUS_MASTER|EFI_PCI_IO_ATTRIBUTE_DUAL_ADDRESS_CYCLE;
 UINT16 Command;
 if(Op==EfiPciIoAttributeOperationGet || Op==EfiPciIoAttributeOperationSupported) {if(!Result)return EFI_INVALID_PARAMETER;*Result=Op==EfiPciIoAttributeOperationGet?mAttributes:Supported;return EFI_SUCCESS;}
 if(Attr&~Supported)return EFI_UNSUPPORTED;
 switch(Op) {case EfiPciIoAttributeOperationEnable:mAttributes|=Attr;break;case EfiPciIoAttributeOperationDisable:mAttributes&=~Attr;break;case EfiPciIoAttributeOperationSet:mAttributes=Attr;break;default:return EFI_UNSUPPORTED;}
 Command=MmioRead16(P5_NVME_ECAM+4)&~6U;
 if(mAttributes&EFI_PCI_IO_ATTRIBUTE_MEMORY)Command|=2;
 if(mAttributes&EFI_PCI_IO_ATTRIBUTE_BUS_MASTER)Command|=4;
 MmioWrite16(P5_NVME_ECAM+4,Command);return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI PollUnsupported(EFI_PCI_IO_PROTOCOL *This,EFI_PCI_IO_PROTOCOL_WIDTH W,UINT8 Bar,UINT64 Off,UINT64 Mask,UINT64 Value,UINT64 Delay,UINT64 *Result) {return EFI_UNSUPPORTED;}
STATIC EFI_STATUS EFIAPI IoUnsupported(EFI_PCI_IO_PROTOCOL *This,EFI_PCI_IO_PROTOCOL_WIDTH W,UINT8 Bar,UINT64 Off,UINTN Count,VOID *Buf) {return EFI_UNSUPPORTED;}
STATIC EFI_STATUS EFIAPI CopyUnsupported(EFI_PCI_IO_PROTOCOL *This,EFI_PCI_IO_PROTOCOL_WIDTH W,UINT8 DstBar,UINT64 Dst,UINT8 SrcBar,UINT64 Src,UINTN Count) {return EFI_UNSUPPORTED;}
STATIC EFI_STATUS EFIAPI GetBar(EFI_PCI_IO_PROTOCOL *This,UINT8 Bar,UINT64 *Supports,VOID **Resources) {return EFI_UNSUPPORTED;}
STATIC EFI_STATUS EFIAPI SetBar(EFI_PCI_IO_PROTOCOL *This,UINT64 Attr,UINT8 Bar,UINT64 *Off,UINT64 *Length) {return EFI_UNSUPPORTED;}
STATIC EFI_PCI_IO_PROTOCOL mPci={.PollMem=PollUnsupported,.PollIo=PollUnsupported,.Mem={MemRead,MemWrite},.Io={IoUnsupported,IoUnsupported},.Pci={ConfigRead,ConfigWrite},.CopyMem=CopyUnsupported,.Map=Map,.Unmap=Unmap,.AllocateBuffer=Allocate,.FreeBuffer=Free,.Flush=Flush,.GetLocation=Location,.Attributes=Attributes,.GetBarAttributes=GetBar,.SetBarAttributes=SetBar};
#pragma pack(1)
STATIC struct {ACPI_HID_DEVICE_PATH Root;PCI_DEVICE_PATH Port,Endpoint;EFI_DEVICE_PATH_PROTOCOL End;} mPath={
 {{ACPI_DEVICE_PATH,ACPI_DP,{sizeof(ACPI_HID_DEVICE_PATH),0}},0x0a0841d0,128},
 {{HARDWARE_DEVICE_PATH,HW_PCI_DP,{sizeof(PCI_DEVICE_PATH),0}},0,0},
 {{HARDWARE_DEVICE_PATH,HW_PCI_DP,{sizeof(PCI_DEVICE_PATH),0}},0,0},
 {END_DEVICE_PATH_TYPE,END_ENTIRE_DEVICE_PATH_SUBTYPE,{4,0}}};
#pragma pack()
EFI_STATUS EFIAPI LwNvmeEntry(EFI_HANDLE Image,EFI_SYSTEM_TABLE *System) {
 EFI_HANDLE Handle=NULL;UINT64 Bar=(UINT64)MmioRead32(P5_NVME_ECAM+0x10)&~15ULL;
 Bar|=(UINT64)MmioRead32(P5_NVME_ECAM+0x14)<<32;
 if(MmioRead32(P5_NVME_ECAM)!=0x00101b36 || Bar!=P5_NVME_BAR)return EFI_UNSUPPORTED;
 mAttributes=EFI_PCI_IO_ATTRIBUTE_MEMORY|EFI_PCI_IO_ATTRIBUTE_BUS_MASTER;
 DEBUG((DEBUG_ERROR,"LWLAB P5 exclusive NVMe ECAM=%lx BAR=%lx\n",(UINT64)P5_NVME_ECAM,Bar));
 return gBS->InstallMultipleProtocolInterfaces(&Handle,&gEfiPciIoProtocolGuid,&mPci,&gEfiDevicePathProtocolGuid,&mPath,NULL);
}
