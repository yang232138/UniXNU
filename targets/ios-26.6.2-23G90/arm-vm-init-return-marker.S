// SPDX-License-Identifier: BSD-2-Clause-Patent
// XNU has replaced the bootstrap TTBR0 by the time arm_vm_init returns.
// Map only display rows 64–79 with XNU's early Device-memory mapper.
// The continuation overwrites x8 before reading it. No other volatile
// values from the preceding void call are live here, except LR and x18.
.text
.global _start
_start:
    adrp    x9, _const_boot_args
    add     x9, x9, :lo12:_const_boot_args
    ldr     x0, [x9, #0x28]
    movz    x8, #0xfc40, lsl #16
    cmp     x0, x8
    b.ne    resume_entry
    ldr     x10, [x9, #0x38]
    mov     x8, #4800
    cmp     x10, x8
    b.ne    resume_entry
    ldr     x10, [x9, #0x40]
    cmp     x10, #1200
    b.ne    resume_entry
    ldr     x10, [x9, #0x48]
    cmp     x10, #80
    b.lo    resume_entry
    ldr     x10, [x9, #0x50]
    and     w10, w10, #0xff
    cmp     w10, #32
    b.ne    resume_entry

    stp     x18, x30, [sp, #-16]!
    add     x0, x0, #0x4b, lsl #12     // 64 * 4800
    movz    x1, #0x3000               // round up 16 * 4800 to 0x13000
    movk    x1, #1, lsl #16
    bl      _ml_io_map
    ldp     x18, x30, [sp], #16
    tbz     x0, #63, resume_entry
    tst     x0, #0xfff
    b.ne    resume_entry

    movz    w10, #0xffff, lsl #16      // opaque red
    movz    w11, #0x4b00               // 16 * 4800 / 4
1:
    str     w10, [x0], #4
    subs    w11, w11, #1
    b.ne    1b
    dsb     sy
resume_entry:
    adrp    x8, _debug_boot_arg
    b       resume
