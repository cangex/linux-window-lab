; SPDX-License-Identifier: MIT
; Permanent low page, excluded from the Windows allocator. INIT/SIPI entry.
bits 16
org 0x6f000
cli
mov ax,cs
mov ds,ax
lgdt [gdtr-$$]
mov eax,cr0
or eax,1
mov cr0,eax
jmp dword 0x08:protected
align 8
gdt: dq 0,0x00cf9a000000ffff,0x00cf92000000ffff
gdtr: dw 23
dd gdt
bits 32
protected:
mov ax,0x10
mov ds,ax
mov es,ax
mov ss,ax
mov eax,1
cpuid
shr ebx,24
cmp ebx,4
jb stopped
cmp ebx,7
ja stopped
lea edi,[ebx*8+0x10000e00]
mov eax,[0x10000e80]
mov edx,[0x10000e84]
mov [edi],eax
mov [edi+4],edx
; Locked operation orders the acknowledgement without requiring SSE setup.
lock or dword [edi],0
stopped:
cli
hlt
jmp stopped
