/* SPDX-License-Identifier: MIT */
#include <windows.h>
BOOL WINAPI DllMain(HINSTANCE h,DWORD reason,LPVOID reserved) {(void)h;(void)reason;(void)reserved;return TRUE;}
__declspec(dllexport) unsigned long lw_value(void) {return 0x50350001;}
