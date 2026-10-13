; SPDX-License-Identifier: GPL-2.0-only
bits 64
default rel
%include "platform.inc"
    cli
    cld
    mov r12,rsi
    mov r13,[r12+72]
    mov rax,0x313030765041574c
    cmp [r12],rax
    jne fail
    cmp dword [r12+8],2
    jne fail
    cmp dword [r12+12],96
    jne fail
    mov rsp,[r12+56]
    xor ebp,ebp
    mov rax,0x313030765041574c
    mov [r13+56],rax
    mov rax,[r12+16]
    mov [r13],rax
    mov eax,0x0b
    xor ecx,ecx
    cpuid
    test ebx,ebx
    jnz .id
    mov eax,1
    cpuid
    mov edx,ebx
    shr edx,24
.id:
    mov [r13+8],edx
    cmp edx,[r12+28]
    jne fail
    mov dword [r13+12],1
    mov rax,[r12+64]
    mov cr3,rax
    mov [r13+40],rax
    mov [r13+48],rsp
    lea rax,[gdt]
    mov [gdtr+2],rax
    lgdt [gdtr]
    push qword 8
    lea rax,[new_cs]
    push rax
    retfq
new_cs:
    mov ax,16
    mov ds,ax
    mov es,ax
    mov ss,ax
    lea rdi, [idt]
    lea rax, [fail]
    mov ecx, 256
.idt_loop:
    mov [rdi], ax
    mov word [rdi+2], 8
    mov word [rdi+4], 0x8e00
    mov rdx, rax
    shr rdx, 16
    mov [rdi+6], dx
    shr rdx, 16
    mov [rdi+8], edx
    mov dword [rdi+12], 0
    add rdi, 16
    loop .idt_loop
    lea rax, [idt]
    mov [idtr+2], rax
    lidt [idtr]
    mov rax,cr0
    and rax,~12
    or rax,2
    mov cr0,rax
    mov rax,cr4
    or rax,0x600
    mov cr4,rax
    fninit
    ldmxcsr [mxcsr]
    mov rcx,LW_HOB
    sub rsp,32
    mov rax,[core_entry]
    call rax
fail:
    mov qword [r13+32],0x100
    mov dword [r13+12],255
.park: cli
    hlt
    jmp .park
align 16
gdt: dq 0,0x00af9a000000ffff,0x00cf92000000ffff
gdtr: dw 23
      dq 0
mxcsr: dd 0x1f80
align 16
; Patched by pack.py; bootstrap binary ends in this unique marker.
core_entry: dq 0x4c57434f52454e54

idtr: dw 4095
       dq 0
align 16
idt: times 4096 db 0
