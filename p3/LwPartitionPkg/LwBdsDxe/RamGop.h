// SPDX-License-Identifier: BSD-2-Clause-Patent
// A partition-owned RAM framebuffer. No access to Linux's VGA/PCI device.
#include <Protocol/GraphicsOutput.h>
#define FB_WIDTH 1024U
#define FB_HEIGHT 768U
#define FB_BYTES (FB_WIDTH * FB_HEIGHT * sizeof(EFI_GRAPHICS_OUTPUT_BLT_PIXEL))
#define FB_ADDRESS (LW_BASE + 0x200000)
STATIC EFI_GRAPHICS_OUTPUT_MODE_INFORMATION mGopInfo = {
  0, FB_WIDTH, FB_HEIGHT, PixelBlueGreenRedReserved8BitPerColor, {0,0,0,0}, FB_WIDTH
};
STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE mGopMode = {
  1, 0, &mGopInfo, sizeof(mGopInfo), FB_ADDRESS, FB_BYTES
};
STATIC EFI_STATUS EFIAPI GopQuery(EFI_GRAPHICS_OUTPUT_PROTOCOL *This, UINT32 Mode,
                                UINTN *Size, EFI_GRAPHICS_OUTPUT_MODE_INFORMATION **Info) {
  if (!Size || !Info) return EFI_INVALID_PARAMETER;
  if (Mode) return EFI_INVALID_PARAMETER;
  *Info=AllocateCopyPool(sizeof(mGopInfo),&mGopInfo);
  if (!*Info) return EFI_OUT_OF_RESOURCES;
  *Size=sizeof(mGopInfo); return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI GopSet(EFI_GRAPHICS_OUTPUT_PROTOCOL *This, UINT32 Mode) {
  if (Mode) return EFI_UNSUPPORTED;
  ZeroMem((VOID *)(UINTN)FB_ADDRESS,FB_BYTES); return EFI_SUCCESS;
}
STATIC BOOLEAN FbRect(UINTN X, UINTN Y, UINTN W, UINTN H) {
  return W && H && W<=FB_WIDTH && H<=FB_HEIGHT && X<=FB_WIDTH-W && Y<=FB_HEIGHT-H;
}
STATIC EFI_STATUS EFIAPI GopBlt(EFI_GRAPHICS_OUTPUT_PROTOCOL *This,
    EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Buffer, EFI_GRAPHICS_OUTPUT_BLT_OPERATION Op,
    UINTN Sx, UINTN Sy, UINTN Dx, UINTN Dy, UINTN W, UINTN H, UINTN Delta) {
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Fb=(VOID *)(UINTN)FB_ADDRESS;
  UINTN X,Y,Row,Bx,By;
  if (Op>=EfiGraphicsOutputBltOperationMax || !W || !H || W>FB_WIDTH || H>FB_HEIGHT)
    return EFI_INVALID_PARAMETER;
  if (Op!=EfiBltVideoToVideo && !Buffer) return EFI_INVALID_PARAMETER;
  if ((Op==EfiBltVideoToBltBuffer || Op==EfiBltVideoToVideo) && !FbRect(Sx,Sy,W,H))
    return EFI_INVALID_PARAMETER;
  if (Op!=EfiBltVideoToBltBuffer && !FbRect(Dx,Dy,W,H)) return EFI_INVALID_PARAMETER;
  if (Op==EfiBltVideoFill) {
    for (Y=0;Y<H;Y++) for (X=0;X<W;X++) Fb[(Dy+Y)*FB_WIDTH+Dx+X]=*Buffer;
  } else if (Op==EfiBltVideoToVideo) {
    for (Y=0;Y<H;Y++) {
      Row=(Dy>Sy)?H-Y-1:Y;
      CopyMem(Fb+(Dy+Row)*FB_WIDTH+Dx,Fb+(Sy+Row)*FB_WIDTH+Sx,W*sizeof(*Fb));
    }
  } else {
    Bx=(Op==EfiBltBufferToVideo)?Sx:Dx;
    By=(Op==EfiBltBufferToVideo)?Sy:Dy;
    if (!Delta) Delta=W*sizeof(*Fb);
    if (Bx>MAX_UINTN/sizeof(*Fb)-W || Delta<(Bx+W)*sizeof(*Fb) ||
        By>MAX_UINTN-H || By+H>MAX_UINTN/Delta) return EFI_INVALID_PARAMETER;
    for (Y=0;Y<H;Y++) {
      VOID *B=(UINT8 *)Buffer+(By+Y)*Delta+Bx*sizeof(*Fb);
      if (Op==EfiBltBufferToVideo) CopyMem(Fb+(Dy+Y)*FB_WIDTH+Dx,B,W*sizeof(*Fb));
      else CopyMem(B,Fb+(Sy+Y)*FB_WIDTH+Sx,W*sizeof(*Fb));
    }
  }
  return EFI_SUCCESS;
}
STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL mGop={GopQuery,GopSet,GopBlt,&mGopMode};
