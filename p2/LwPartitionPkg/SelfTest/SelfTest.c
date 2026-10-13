// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <Uefi.h>
#include <Guid/Acpi.h>
#include <Guid/EventGroup.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/DevicePathLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <LwLab.h>
STATIC EFI_GUID mVarGuid={0x71418e12,0x7141,0x4491,{0x90,0x21,0x78,0x17,0x92,0x44,0x17,0x91}};
STATIC UINTN mExitCount;
STATIC VOID EFIAPI OnExit(EFI_EVENT Event,VOID *Context) { mExitCount++; }
STATIC VOID Check(BOOLEAN Good,UINT64 Case) { if (!Good) LwFail(Case,1); }
STATIC VOID Ok(EFI_STATUS Status,UINT64 Case) { if(EFI_ERROR(Status)) LwFail(Case,Status); }
STATIC VOID Passed(UINTN Bit) { LW_MBOX->Checks|=1ULL<<Bit; DEBUG((DEBUG_INFO,"LWLAB CHECK %u PASS\n",Bit)); }
STATIC UINT8 Sum(VOID *Data,UINTN Size) { UINT8 R=0; UINTN I; for(I=0;I<Size;I++) R+=((UINT8*)Data)[I]; return R; }
STATIC UINT32 U32(UINT8 *P) { UINT32 V;CopyMem(&V,P,4);return V; }
STATIC UINT64 U64(UINT8 *P) { UINT64 V;CopyMem(&V,P,8);return V; }
STATIC UINT8 *Table(UINT64 Address) {
 UINT8 *P=(VOID*)(UINTN)Address; UINT32 N;
 Check(Address>=LW_ACPI && Address<LW_ACPI+0x10000-36,0x511);
 N=U32(P+4); Check(N>=36 && N<=LW_ACPI+0x10000-Address,0x512); Check(Sum(P,N)==0,0x513); return P;
}
EFI_STATUS EFIAPI P2Main(EFI_HANDLE Image,EFI_SYSTEM_TABLE *System) {
 EFI_STATUS S; EFI_LOADED_IMAGE_PROTOCOL *Loaded; EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
 EFI_FILE_PROTOCOL *Root,*File; EFI_DEVICE_PATH_PROTOCOL *Path; EFI_HANDLE Child;
 EFI_EVENT Timer,ExitEvent; EFI_PHYSICAL_ADDRESS Pages; EFI_MEMORY_DESCRIPTOR *Map,*D;
 EFI_RUNTIME_SERVICES *Rt; UINTN I,N,MapBytes,Key,DescSize,Capacity=65536,Index; UINT32 Version,Attrs;
 UINT64 Value=0x7061727475656669ULL,ReadValue,Ticks; UINT8 Data[64],*R,*X,*T; UINTN Found=0; UINT32 A,B,C,E;
 LW_MBOX->Phase=5; LW_MBOX->SystemTable=(UINTN)System;
 AsmCpuid(1,&A,&B,&C,&E); Check((B>>24)==LW_APIC && LW_HAND->Version==2,0x501);
 Ok(gBS->HandleProtocol(Image,&gEfiLoadedImageProtocolGuid,(VOID**)&Loaded),0x502);
 Check((UINTN)Loaded->ImageBase>=LW_BASE && (UINTN)Loaded->ImageBase+Loaded->ImageSize<=LW_END,0x503); Passed(0);
 R=NULL; for(I=0;I<System->NumberOfTableEntries;I++) if(CompareGuid(&System->ConfigurationTable[I].VendorGuid,&gEfiAcpi20TableGuid)) R=System->ConfigurationTable[I].VendorTable;
 Check((UINTN)R==LW_ACPI && CompareMem(R,"RSD PTR ",8)==0 && Sum(R,20)==0 && Sum(R,36)==0,0x510);
 LW_MBOX->Rsdp=(UINTN)R; X=Table(U64(R+24)); Check(CompareMem(X,"XSDT",4)==0 && U32(X+4)==60,0x514);
 for(I=36;I<60;I+=8) {
  T=Table(U64(X+I));
  if(CompareMem(T,"APIC",4)==0) { Check(U32(T+4)==52 && U32(T+36)==LW_LAPIC && U32(T+40)==0 && T[44]==0 && T[45]==8 && T[46]==LW_APIC && T[47]==LW_APIC && U32(T+48)==1,0x515);Found|=1; }
  else if(CompareMem(T,"FACP",4)==0) { Check(U32(T+4)==276 && (U32(T+112)&BIT20)!=0 && U32(T+48)==0 && U32(T+56)==0 && U64(T+116)==0,0x516); Table(U64(T+140));Found|=2; }
  else if(CompareMem(T,"SRAT",4)==0) { Check(U32(T+4)==104 && T[48]==0 && T[50]==1 && T[51]==LW_APIC && T[64]==1 && U32(T+66)==0 && U64(T+72)==LW_BASE && U64(T+80)==LW_SIZE,0x517);Found|=4; }
  else LwFail(0x518,1);
 }
 Check(Found==7,0x519);Passed(1);
 Ok(gBS->AllocatePages(AllocateAnyPages,EfiLoaderData,4,&Pages),0x520);
 Check(Pages>=LW_FREE && Pages+16384<=LW_END,0x521); SetMem((VOID*)(UINTN)Pages,16384,0xa5); Ok(gBS->FreePages(Pages,4),0x522);
 Pages=LW_BASE-4096; S=gBS->AllocatePages(AllocateAddress,EfiLoaderData,1,&Pages); Check(S==EFI_NOT_FOUND,0x523);
 Pages=LW_BASE-1; S=gBS->AllocatePages(AllocateMaxAddress,EfiLoaderData,1,&Pages); Check(S==EFI_OUT_OF_RESOURCES,0x524);
 Ok(gBS->AllocatePool(EfiLoaderData,Capacity,(VOID**)&Map),0x525); MapBytes=Capacity;
 Ok(gBS->GetMemoryMap(&MapBytes,Map,&Key,&DescSize,&Version),0x526); Check(DescSize>=sizeof(*D),0x527);
 LW_MBOX->AllocLow=LW_END; LW_MBOX->AllocHigh=LW_BASE;
 for(I=0;I<MapBytes;I+=DescSize) { D=(VOID*)((UINT8*)Map+I); Check(D->PhysicalStart>=LW_BASE && D->PhysicalStart<LW_END && D->NumberOfPages<=(LW_END-D->PhysicalStart)/4096,0x528);
  if(D->Type==EfiConventionalMemory) { if(D->PhysicalStart<LW_MBOX->AllocLow)LW_MBOX->AllocLow=D->PhysicalStart; if(D->PhysicalStart+D->NumberOfPages*4096>LW_MBOX->AllocHigh)LW_MBOX->AllocHigh=D->PhysicalStart+D->NumberOfPages*4096; }
 }
 Passed(2);
 Ok(gBS->HandleProtocol(Loaded->DeviceHandle,&gEfiSimpleFileSystemProtocolGuid,(VOID**)&Fs),0x530); Ok(Fs->OpenVolume(Fs,&Root),0x531);
 Ok(Root->Open(Root,&File,L"\\MARKER.TXT",EFI_FILE_MODE_READ,0),0x532); N=sizeof(Data); Ok(File->Read(File,&N,Data),0x533);
 Check(N==30 && CompareMem(Data,"LWLAB P2 partition-only file\r\n",30)==0,0x534); N=1;S=File->Write(File,&N,Data);Check(S==EFI_ACCESS_DENIED || S==EFI_WRITE_PROTECTED,0x535); Ok(File->Close(File),0x536);Ok(Root->Close(Root),0x537);Passed(3);
 Path=FileDevicePath(Loaded->DeviceHandle,L"\\P2CHILD.EFI");Check(Path!=NULL,0x540);Ok(gBS->LoadImage(FALSE,Image,Path,NULL,0,&Child),0x541);Ok(gBS->FreePool(Path),0x542);
 Ok(gBS->StartImage(Child,NULL,NULL),0x543);Check(LW_MBOX->Phase==0xc11d,0x544);Passed(4);
 Ticks=LW_MBOX->TimerTicks; Ok(gBS->CreateEvent(EVT_TIMER,TPL_APPLICATION,NULL,NULL,&Timer),0x550);Ok(gBS->SetTimer(Timer,TimerPeriodic,200000),0x551);
 for(I=0;I<100;I++) Ok(gBS->WaitForEvent(1,&Timer,&Index),0x552);
 Ok(gBS->SetTimer(Timer,TimerCancel,0),0x553);Ok(gBS->CloseEvent(Timer),0x554);Check(LW_MBOX->TimerTicks>Ticks,0x555);Passed(5);
 Attrs=EFI_VARIABLE_NON_VOLATILE|EFI_VARIABLE_BOOTSERVICE_ACCESS|EFI_VARIABLE_RUNTIME_ACCESS;
 Ok(gRT->SetVariable(L"P2Probe",&mVarGuid,Attrs,sizeof(Value),&Value),0x560);N=1;S=gRT->GetVariable(L"P2Probe",&mVarGuid,NULL,&N,&ReadValue);Check(S==EFI_BUFFER_TOO_SMALL && N==8,0x561);
 Ok(gRT->GetVariable(L"P2Probe",&mVarGuid,&Attrs,&N,&ReadValue),0x562);Check(ReadValue==Value,0x563);Passed(6);
 Ok(gBS->CreateEventEx(EVT_NOTIFY_SIGNAL,TPL_NOTIFY,OnExit,NULL,&gEfiEventExitBootServicesGuid,&ExitEvent),0x570);
 MapBytes=Capacity;Ok(gBS->GetMemoryMap(&MapBytes,Map,&Key,&DescSize,&Version),0x571);
 S=gBS->ExitBootServices(Image,Key+1);Check(S==EFI_INVALID_PARAMETER,0x572);
 // Only memory map / ExitBootServices calls follow the first exit attempt.
 MapBytes=Capacity;Ok(gBS->GetMemoryMap(&MapBytes,Map,&Key,&DescSize,&Version),0x573);
 Rt=gRT; S=gBS->ExitBootServices(Image,Key);if(EFI_ERROR(S))LwFail(0x574,S);
 DisableInterrupts();Check(mExitCount>0,0x575);LW_MBOX->Checks|=BIT7;
 for(I=0;I<MapBytes;I+=DescSize) { D=(VOID*)((UINT8*)Map+I); D->VirtualStart=(D->Attribute & EFI_MEMORY_RUNTIME) ? D->PhysicalStart+LW_VIRTUAL_OFFSET : 0; }
 S=Rt->SetVirtualAddressMap(MapBytes,DescSize,Version,Map);if(EFI_ERROR(S))LwFail(0x580,S);
 Rt=(VOID*)((UINTN)Rt+LW_VIRTUAL_OFFSET);Check((UINTN)Rt->GetVariable>=LW_BASE+LW_VIRTUAL_OFFSET && (UINTN)Rt->GetVariable<LW_END+LW_VIRTUAL_OFFSET,0x581);
 N=8;S=Rt->GetVariable(L"P2Probe",&mVarGuid,&Attrs,&N,&ReadValue);if(EFI_ERROR(S))LwFail(0x582,S);Check(ReadValue==Value,0x583);
 Value++;S=Rt->SetVariable(L"P2Probe",&mVarGuid,Attrs,8,&Value);if(EFI_ERROR(S))LwFail(0x584,S);
 N=8;S=Rt->GetVariable(L"P2Probe",&mVarGuid,NULL,&N,&ReadValue);if(EFI_ERROR(S))LwFail(0x585,S);Check(ReadValue==Value,0x586);
 LW_MBOX->Checks|=BIT8; LW_MBOX->Phase=9;LW_MBOX->Heartbeat=1;MemoryFence();LW_MBOX->Stage=2;
 for(;;) { LW_MBOX->Tsc=AsmReadTsc(); LW_MBOX->Heartbeat++; CpuPause(); }
}
