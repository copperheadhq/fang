# firmware

[`qo-r1/`](qo-r1/) is the Quiet Orbit QO-R1 firmware exactly as
copperheadhq/copperhead-quiet-orbit publishes it at `056933b`: `main.c`,
`led_pwm.c`, `led_pwm.h`, `pins.h`, its `Makefile` and its `README.md`. It is
QO-R1's, under QO-R1's licence, GPL-3.0-only, whose text is
[`qo-r1/LICENSE`](qo-r1/LICENSE). So is the ELF under [`elf/`](elf/), which
is that source built, and whose corresponding source is `qo-r1/`. Both sit
beside fang's code as an aggregate: fang's Apache-2.0 licence does not cover
them, and nothing in fang links them.

The [`Makefile`](Makefile) here, which runs QO-R1's and keeps the ELF, and
[`TOOLCHAIN`](TOOLCHAIN), the toolchain that built it and the digest it
rebuilds to, are fang's.
