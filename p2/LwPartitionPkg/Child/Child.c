// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <Uefi.h>
#include <LwLab.h>
EFI_STATUS EFIAPI ChildMain(EFI_HANDLE Image,EFI_SYSTEM_TABLE *System) {
 if (!Image || System->Hdr.Signature!=EFI_SYSTEM_TABLE_SIGNATURE) return EFI_INVALID_PARAMETER;
 LW_MBOX->Phase=0xc11d;return EFI_SUCCESS;
}
