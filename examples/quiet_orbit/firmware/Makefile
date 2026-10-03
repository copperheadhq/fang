# The Quiet Orbit QO-R1 firmware, built by its own Makefile.
#
# qo-r1/ is QO-R1's firmware exactly as published, under its own licence
# (qo-r1/LICENSE, GPL-3.0-only); this Makefile is fang's, and only runs that
# one and keeps the ELF. Needs avr-gcc and avr-libc on the path. The ELF is
# committed, so nothing in the fang suite rebuilds it; `make` reproduces it
# byte for byte with the toolchain named in TOOLCHAIN.

ELF = elf/quiet-orbit-qo-r1.elf

all: $(ELF)

$(ELF): qo-r1/main.c qo-r1/led_pwm.c qo-r1/led_pwm.h qo-r1/pins.h qo-r1/Makefile | elf
	$(MAKE) -C qo-r1 quiet-orbit-qo-r1.elf
	cp qo-r1/quiet-orbit-qo-r1.elf $@
	$(MAKE) -C qo-r1 clean

elf:
	mkdir -p elf

clean:
	rm -f $(ELF)

.PHONY: all clean
