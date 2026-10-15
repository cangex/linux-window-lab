// SPDX-License-Identifier: BSD-2-Clause-Patent
// Experimental, version-pinned Windows HAL data adaptation. No instruction
// bytes are modified. LW_HAL_IPI_MODE: 1 = read-only probe, 2 = enforce.
// Windows 26100.1742 ntoskrnl.exe SHA256:
// 93db70780a95192d13d04b4c3cb49c22a138063adba5c83d4855be02b645fdd0
// PDB 953A8DE880B0818C32DA2DEC1D79C2D91, age 1:
// HalpInterruptNoShorthand = section 26 + 64540 = RVA 0xe0fc1c.
// This internal HAL flag is NOT a supported Microsoft configuration API.
#define LW_HAL_IMAGE_SIZE 0x144f000U
#define LW_HAL_FLAG_RVA 0xe0fc1cU
STATIC BOOLEAN LwHalImage(UINT8 *B) {
  STATIC CONST UINT8 Rsds[] = {
    0x52,0x53,0x44,0x53,0xe8,0x8d,0x3a,0x95,0xb0,0x80,0x8c,0x81,
    0x32,0xda,0x2d,0xec,0x1d,0x79,0xc2,0xd9,0x01,0x00,0x00,0x00
  };
  // RIP-relative instructions are unaffected by image relocation. This guard
  // checks the broadcast-excluding-self branch and its NoShorthand test.
  STATIC CONST UINT8 Branch[] = {
    0x41,0x8b,0x82,0xf4,0,0,0,0xa8,0x20,0x74,0x19,
    0x80,0x3d,0xb1,0xbd,0xb8,0,0,0x75,0x10,
    0xc7,0x84,0x24,0x90,0,0,0,0x02,0,0,0
  };
  UINT32 Pe;
  if (ReadUnaligned16((UINT16 *)B)!=0x5a4d) return FALSE;
  Pe=ReadUnaligned32((UINT32 *)(B+0x3c));
  if (Pe>0x800 || ReadUnaligned32((UINT32 *)(B+Pe))!=0x4550 ||
      ReadUnaligned16((UINT16 *)(B+Pe+4))!=0x8664 ||
      ReadUnaligned32((UINT32 *)(B+Pe+8))!=0xd98db6a6 ||
      ReadUnaligned16((UINT16 *)(B+Pe+24))!=0x20b ||
      ReadUnaligned32((UINT32 *)(B+Pe+24+56))!=LW_HAL_IMAGE_SIZE) return FALSE;
  return CompareMem(B+0x5783c,Rsds,sizeof(Rsds))==0 &&
         CompareMem(B+0x283e59,Branch,sizeof(Branch))==0;
}
STATIC VOID LwHalIpiConfigure(VOID) {
  // Only partition-owned identity-mapped RAM. Never scan Linux or MMIO.
  STATIC CONST UINT64 Ranges[][2] = {
    {0x10000000ULL,0x70000000ULL}, {0x280000000ULL,0x400000000ULL}
  };
  UINTN I,Count=0; UINT64 At,Found=0; volatile UINT8 *Flag;
  for (I=0;I<ARRAY_SIZE(Ranges);I++) {
    for (At=Ranges[I][0];At+LW_HAL_IMAGE_SIZE<=Ranges[I][1];At+=4096) {
      if (LwHalImage((UINT8 *)(UINTN)At)) { Found=At; Count++; }
    }
  }
  DEBUG((DEBUG_ERROR,"LWLAB P6 HAL probe matches=%lu image=%lx mode=%u\n",Count,Found,LW_HAL_IPI_MODE));
  if (Count!=1) {
    if (LW_HAL_IPI_MODE==2) LwFail(0x610,EFI_COMPROMISED_DATA);
    return;
  }
  Flag=(volatile UINT8 *)(UINTN)(Found+LW_HAL_FLAG_RVA);
  DEBUG((DEBUG_ERROR,"LWLAB P6 HAL NoShorthand address=%lx before=%u\n",(UINT64)(UINTN)Flag,(UINT32)*Flag));
  if (LW_HAL_IPI_MODE==2) {
    if (*Flag!=0) LwFail(0x611,EFI_COMPROMISED_DATA);
    *Flag=1; MemoryFence();
    if (*Flag!=1) LwFail(0x612,EFI_DEVICE_ERROR);
    DEBUG((DEBUG_ERROR,"LWLAB P6 HAL NoShorthand enforced=1 version=26100.1742\n"));
  }
}
