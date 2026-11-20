// SPDX-License-Identifier: BSD-2-Clause-Patent
// Boot CPU at arm_init(boot_args *) or before arm_vm_init(size, boot_args *).
// Keep the call arguments, LR, x18, the stack and all callee-saved registers.
// Restore the empty TTBR0 leaf before resuming XNU.
.text
.global _start
_start:
.ifdef ARM_VM_INIT_MARKER
    mov     x8, x1
    bootargs .req x8
.else
    bootargs .req x0
.endif
    ldr     x1, [bootargs, #0x28]
    movz    x2, #0xfc40, lsl #16
    cmp     x1, x2
    b.ne    resume_entry
    ldr     x2, [bootargs, #0x38]
    movz    x3, #4800
    cmp     x2, x3
    b.ne    resume_entry
    ldr     x2, [bootargs, #0x48]
.ifdef ARM_VM_INIT_MARKER
    cmp     x2, #64
.else
    cmp     x2, #32
.endif
    b.lo    resume_entry

    mrs     x3, ttbr0_el1
    and     x3, x3, #0x0000fffffffff000
    ubfx    x4, x1, #30, #8
    ldr     x3, [x3, x4, lsl #3]
    and     x4, x3, #3
    cmp     x4, #3
    b.ne    resume_entry
    and     x3, x3, #0x0000fffffffff000
    ubfx    x4, x1, #21, #9
    add     x3, x3, x4, lsl #3
    ldr     x4, [x3]
    cbnz    x4, resume_entry

    // 2 MiB block, EL1 RW, PXN/UXN, AF, MAIR slot 3 (Device-nGnRnE).
    movz    x4, #0x40d
    movk    x4, #0x60, lsl #48
    orr     x4, x4, x1
    str     x4, [x3]
    lsr     x5, x1, #12
    dsb     ishst
    tlbi    vaae1is, x5
    dsb     ish
    isb

    // Paint 32 lines at 4800 bytes per line. Cyan starts below orange.
.ifdef ARM_VM_INIT_MARKER
    add     x1, x1, #0x25, lsl #12
    add     x1, x1, #0x800
    movz    w6, #0xffff
    movk    w6, #0xff00, lsl #16
.else
    movz    w6, #0xa500
    movk    w6, #0xffff, lsl #16
.endif
    movz    w7, #0x9600
1:
    str     w6, [x1], #4
    subs    w7, w7, #1
    b.ne    1b
    dsb     sy
    str     xzr, [x3]
    dsb     ishst
    tlbi    vaae1is, x5
    dsb     ish
    isb
resume_entry:
.ifdef ARM_VM_INIT_MARKER
    mov     x1, x8
.else
    pacibsp
.endif
    b       resume
