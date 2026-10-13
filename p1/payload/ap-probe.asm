; SPDX-License-Identifier: GPL-2.0-only
; Flat x86-64 PIC payload. RSI is a physical lw_handoff pointer.
bits 64
default rel
entry:
    cli
    cld
    mov r12, rsi
    mov r13, [r12+72]
    mov rax, 0x313030765041574c
    cmp [r12], rax
    jne bad_header
    cmp dword [r12+8], 1
    jne bad_header
    cmp dword [r12+12], 88
    jne bad_header
    mov rsp, [r12+56]
    xor ebp, ebp
    mov rax, [r12+16]
    mov [r13], rax
    mov eax, 0x0b
    xor ecx, ecx
    cpuid
    test ebx, ebx
    jnz .apic_found
    mov eax, 1
    cpuid
    mov edx, ebx
    shr edx, 24
.apic_found:
    mov [r13+8], edx
    cmp edx, [r12+28]
    jne bad_apic
    mov dword [r13+12], 1
    mov rax, [r12+64]
    mov cr3, rax
    mov [r13+40], rax
    mov [r13+48], rsp
    lea rax, [gdt]
    mov [gdtr+2], rax
    lgdt [gdtr]
    push qword 8
    lea rax, [new_cs]
    push rax
    retfq
new_cs:
    mov ax, 16
    mov ds, ax
    mov es, ax
    mov ss, ax
    lea rdi, [idt]
    lea rax, [exception]
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
    cmp qword [r12+80], 1
    je park                  ; test: entered but never ready
    cmp qword [r12+80], 2
    jne .ready
    ud2                      ; test: record an exception, never claim ready
.ready:
    mov rax, 0x313030765041574c
    mov [r13+56], rax
    mov qword [r13+16], 1
    sfence
    mov dword [r13+12], 2
.heartbeat:
    mov ecx, 100000
.delay:
    pause
    loop .delay
    rdtsc
    shl rdx, 32
    or rax, rdx
    mov [r13+24], rax
    inc qword [r13+16]
    jmp .heartbeat
bad_header:
    mov qword [r13+32], 1
    jmp failed
bad_apic:
    mov qword [r13+32], 2
    jmp failed
exception:
    mov qword [r13+32], 3
failed:
    sfence
    mov dword [r13+12], 255
park:
    cli
    hlt
    jmp park
align 16
gdt: dq 0, 0x00af9a000000ffff, 0x00cf92000000ffff
gdtr: dw 23
      dq 0
idtr: dw 4095
      dq 0
align 16
idt: times 4096 db 0
