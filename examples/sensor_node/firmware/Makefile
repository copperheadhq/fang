# The sensor_node firmware and its three defective builds.
#
# Needs arm-none-eabi-gcc on the path. The ELFs are committed beside the
# source, so nothing in the fang suite rebuilds them; `make` reproduces them
# byte for byte with the toolchain named in TOOLCHAIN.

CC      = arm-none-eabi-gcc
CFLAGS  = -mcpu=cortex-m4 -mthumb -mfloat-abi=soft -O2 -std=c11 \
          -ffreestanding -fno-builtin -ffunction-sections -fdata-sections \
          -Wall -Wextra -Werror -g0
LDFLAGS = -nostdlib -T stm32f401re.ld -Wl,--gc-sections -Wl,--build-id=none

SOURCES = src/startup.c src/main.c

BUILDS  = elf/sensor_node.elf elf/wrong_address.elf \
          elf/push_pull.elf elf/no_timeout.elf

all: $(BUILDS)

elf/sensor_node.elf: $(SOURCES) stm32f401re.ld | elf
	$(CC) $(CFLAGS) $(LDFLAGS) $(SOURCES) -o $@

elf/wrong_address.elf: $(SOURCES) stm32f401re.ld | elf
	$(CC) $(CFLAGS) -DSENSOR_ADDRESS=0x45 $(LDFLAGS) $(SOURCES) -o $@

elf/push_pull.elf: $(SOURCES) stm32f401re.ld | elf
	$(CC) $(CFLAGS) -DI2C_PUSH_PULL $(LDFLAGS) $(SOURCES) -o $@

elf/no_timeout.elf: $(SOURCES) stm32f401re.ld | elf
	$(CC) $(CFLAGS) -DNO_TIMEOUT $(LDFLAGS) $(SOURCES) -o $@

elf:
	mkdir -p elf

clean:
	rm -f $(BUILDS)

.PHONY: all clean
