# quiet_orbit: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.fades_as_shipped (`REQ-7cd8d72c6076`)

> Programmed over ISP with its firmware and nothing else, on a part with the fuses it ships with, the four LEDs fade as they do with the fuse set

MUST, state KNOWN, validation by emulation.

- Verified by `system.as_shipped` (`VER-c3806df90a0a`): **UNKNOWN** by emulation

### system.fades (`REQ-8dc78b059fd5`)

> Programmed with the low fuse 0xE2, as its firmware's README directs, the four LEDs fade on hardware PWM at the firmware's 488 Hz, a quarter cycle apart, each fully lit in turn SE, NE, NW and SW

MUST, state KNOWN, validation by emulation.

- Verified by `system.orbit` (`VER-7ebda182a450`): **UNKNOWN** by emulation

## Evidence

### system.readme_fuse (`EVD-01cd1266a7ed`)

> The ATtiny84A arrives blank and runs on its internal 8 MHz RC oscillator. If your part ships with the clock divided by 8, change that fuse; nothing else needs changing

Cited from SRC-QO-R1, README.md, Building it; firmware/README.md: F_CPU=8000000UL.

### system.mcu.shipped_clock (`EVD-215e59e608b6`)

> The device is shipped with CKSEL = 0010, SUT = 10 and CKDIV8 programmed: the internal oscillator at 8.0 MHz with an initial system clock prescaling of 8, a 1.0 MHz system clock; the fuse low byte defaults to 0x62

Cited from SRC-DS-ATTINY84A, DS40002269A, section 6.2.6 (default clock source), p. 36; table 19-5 (fuse low byte), p. 166.

### system.leds_on_pwm (`EVD-328cc44aadf2`)

> Each LED SHALL have its own series resistor and its own MCU pin with a hardware PWM output, permitting four simultaneous independent fades

Cited from SRC-QO-R1, docs/SPEC.md, light output; docs/PINOUT.md, LED channel mapping.

### system.mcu.part_number (`EVD-32c48224a431`)

> ATTINY84A-SSU is the ATtiny84A in a 14-lead SOIC (150 mil), -40 to 85 C

Cited from SRC-DS-ATTINY84A, DS40002269A, section 27 (ordering information).

### system.mcu.compare_outputs (`EVD-44c39bdf8a99`)

> OC0A is PB2, OC0B is PA7, OC1A is PA6 and OC1B is PA5; PA6 is also MOSI, PA5 MISO and PA4 SCK

Cited from SRC-DS-ATTINY84A, DS40002269A, sections 10.2.1 and 10.2.2 (alternate functions of ports A and B), pp. 66-70.

### system.mcu.pinout (`EVD-56c681b86b64`)

> SOIC-14: 1 VCC, 2 PB0, 3 PB1, 4 PB3 (RESET), 5 PB2, 6 PA7, 7 PA6, 8 PA5, 9 PA4, 10 PA3, 11 PA2, 12 PA1, 13 PA0, 14 GND

Cited from SRC-DS-ATTINY84A, DS40002269A, figure 1-1 (pinout of ATtiny24A/44A/84A), p. 8.
