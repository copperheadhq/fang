# Firmware for the simavr runner's tests, one ELF per build flag.
#
# Needs avr-gcc and avr-libc on the path. The ELFs are committed beside the
# source, so nothing in the fang suite rebuilds them; `make` reproduces them
# byte for byte with the toolchain named in TOOLCHAIN.

CC      = avr-gcc
CFLAGS  = -mmcu=attiny84 -DF_CPU=8000000UL -std=c11 -Os -Wall -Wextra -Werror \
          -ffunction-sections -fdata-sections
LDFLAGS = -mmcu=attiny84 -Wl,--gc-sections

SOURCE  = src/fixtures.c
BUILDS  = elf/blink.elf elf/pins.elf elf/prescaler.elf elf/late.elf \
          elf/osccal.elf elf/prtim1.elf elf/halt.elf

all: $(BUILDS)

elf/blink.elf: $(SOURCE) | elf
	$(CC) $(CFLAGS) -DFIX_BLINK $(LDFLAGS) $(SOURCE) -o $@

elf/pins.elf: $(SOURCE) | elf
	$(CC) $(CFLAGS) -DFIX_PINS $(LDFLAGS) $(SOURCE) -o $@

elf/prescaler.elf: $(SOURCE) | elf
	$(CC) $(CFLAGS) -DFIX_PRESCALER $(LDFLAGS) $(SOURCE) -o $@

elf/late.elf: $(SOURCE) | elf
	$(CC) $(CFLAGS) -DFIX_LATE $(LDFLAGS) $(SOURCE) -o $@

elf/osccal.elf: $(SOURCE) | elf
	$(CC) $(CFLAGS) -DFIX_OSCCAL $(LDFLAGS) $(SOURCE) -o $@

elf/prtim1.elf: $(SOURCE) | elf
	$(CC) $(CFLAGS) -DFIX_PRTIM1 $(LDFLAGS) $(SOURCE) -o $@

elf/halt.elf: $(SOURCE) | elf
	$(CC) $(CFLAGS) -DFIX_HALT $(LDFLAGS) $(SOURCE) -o $@

elf:
	mkdir -p elf

clean:
	rm -f $(BUILDS)

.PHONY: all clean
