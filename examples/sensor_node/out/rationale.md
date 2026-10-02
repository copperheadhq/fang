# sensor_node — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.survives_missing_sensor — `REQ-a2382492c60d`

> With the HS3001 missing the firmware keeps running and blinks the status LED fast, and makes no read

MUST, state KNOWN, validation by emulation.

- Verified by `system.sensor_missing` (`VER-607ca20f775b`): **UNKNOWN** by emulation

### system.sensor_ready — `REQ-c59ecf950435`

> Within 200 ms of reset the firmware reads the HS3001, reports the temperature it read on the console, and blinks the status LED slowly while readings succeed

MUST, state KNOWN, validation by emulation.

- Verified by `system.startup` (`VER-eda715fc0af6`): **UNKNOWN** by emulation

## Decisions

### connection.0004.line.right — `DEC-022639c73f2d`

**Which pin of `system.mcu` carries electrical.line?** → `system.mcu.PB8` (`PIN-6093c2974cd4`)

- first candidate in the part's declared preference order that was not already assigned within this lowering
- Rejected alternative: a higher-preference candidate was available

### connection.0006.line.right — `DEC-646a4bf67d93`

**Which pin of `system.mcu` carries electrical.line?** → `system.mcu.PB9` (`PIN-55f9f908a69a`)

- first candidate in the part's declared preference order that was not already assigned within this lowering
- Rejected alternative: a higher-preference candidate was available

### connection.0002.sda.left — `DEC-7590c395f3db`

**Which pin of `system.mcu` carries i2c.sda?** → `system.mcu.PB9` (`PIN-55f9f908a69a`)

- first candidate in the part's declared preference order that was not already assigned within this lowering
- Rejected alternative: a higher-preference candidate was available

### connection.0002.scl.left — `DEC-ac2aa404adb6`

**Which pin of `system.mcu` carries i2c.scl?** → `system.mcu.PB8` (`PIN-6093c2974cd4`)

- first candidate in the part's declared preference order that was not already assigned within this lowering
- Rejected alternative: a higher-preference candidate was available

## Evidence

### system.decoupling — `EVD-114c55433d48`

> Each VDD/VSS pair is decoupled with ceramic capacitors close to the pins; the scheme shows 6 x 100 nF and 1 x 4.7 uF across the VDD pins

Cited from SRC-DS-STM32F401, DS10086 Rev 5, figure 18 (power supply scheme), section 6.1.6, p. 57.

### system.mcu.part_number — `EVD-32c48224a431`

> STM32F401RET6 is 64 pins (R), 512 Kbytes of Flash (E), LQFP (T), -40 to 85 C (6)

Cited from SRC-DS-STM32F401, DS10086 Rev 5, table 87 (ordering information scheme), p. 132; table 88 (device order codes), p. 133.

### system.mcu.af_table — `EVD-355c4bf2d94a`

> I2C1_SCL is AF4 on PB6 and PB8, I2C1_SDA is AF4 on PB7 and PB9; USART2_TX is AF7 on PA2 and USART2_RX is AF7 on PA3

Cited from SRC-DS-STM32F401, DS10086 Rev 5, table 9 (alternate function mapping), pp. 45-46.

### system.mcu.io_levels — `EVD-4d433ebb43b4`

> FT I/O, 1.7 V <= VDD <= 3.6 V: VIL max 0.3 VDD, VIH min 0.7 VDD. CMOS port at IIO = 8 mA, 2.7 V <= VDD <= 3.6 V: VOL max 0.4 V, VOH min VDD - 0.4 V

Cited from SRC-DS-STM32F401, DS10086 Rev 5, table 54 (I/O static characteristics), p. 91; table 55 (output voltage characteristics), p. 94.

### system.env.i2c_rate — `EVD-562d5ac7826f`

> SCL clock frequency up to 400 kHz

Cited from SRC-DS-HS3XXX, R36DS0045EU0101 Rev 1.01, table 1 (I2C timing parameters), p. 10.

### system.mcu.pinout — `EVD-56c681b86b64`

> LQFP64 pins: PA2 16, PA3 17, PA5 21, PB6 58, PB7 59, PB8 61, PB9 62, VSS 63, VDD 64; PA2, PA3, PA5 and PB6 to PB9 are 5 V tolerant (FT) I/O

Cited from SRC-DS-STM32F401, DS10086 Rev 5, table 8 (pin definitions), pp. 38-44; figure 12 (LQFP64 pinout), p. 35.

### system.env.fixed_address — `EVD-7b21ee48ef6d`

> The HS3xxx series I2C address is 0x44, and the device responds only to this 7-bit address; a custom address is available on request

Cited from SRC-DS-HS3XXX, R36DS0045EU0101 Rev 1.01, section 7.2 (sensor slave address), p. 10.

### system.env.application — `EVD-81f30ef39bc1`

> Pull-up resistors to VDD are required on SCL and SDA, 2.2 kOhm typical; 0.1 uF from VC to ground and 0.1 uF from VDD to ground

Cited from SRC-DS-HS3XXX, R36DS0045EU0101 Rev 1.01, section 6, figure 13 (application circuit), p. 9; section 7, p. 10.

### system.mcu.i2c_rate — `EVD-9b5504fe726a`

> The I2C interface supports standard mode, up to 100 kHz, and fast mode, up to 400 kHz

Cited from SRC-DS-STM32F401, DS10086 Rev 5, section 6.3.19 (I2C interface characteristics), p. 98.

### system.env.pinout — `EVD-d5b7c93c04cc`

> 6-LGA, 3.0 x 2.41 mm: 1 SCL, 2 SDA, 3 VC (0.1 uF to ground), 4 VDD, 5 NC (do not connect), 6 VSS

Cited from SRC-DS-HS3XXX, R36DS0045EU0101 Rev 1.01, section 1.2 and figure 1 (pin assignments), p. 4.
