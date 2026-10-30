/* Startup for model/spike_xcheck.py. s0 walks the signature region; the
 * generated vectors.S stores one result word per vector and jumps to done.
 * Writing 1 to tohost tells Spike to exit with code 0, and Spike then dumps
 * begin_signature..end_signature to the +signature file. */
    .section .text.init
    .globl _start
_start:
    la    s0, begin_signature
    j     run_vectors

    .globl done
done:
    li    t0, 1
    la    t1, tohost
    sw    t0, 0(t1)
    sw    zero, 4(t1)
1:  j     1b

    .section .tohost, "aw", @progbits
    .align 6
    .globl tohost
tohost:   .dword 0
    .align 6
    .globl fromhost
fromhost: .dword 0
