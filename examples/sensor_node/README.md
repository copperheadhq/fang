# sensor_node

An STM32F401RE reading an HS3001 humidity sensor over I2C1, with a serial
console on USART2 and a status LED on PA5. Read it after
[`sensor_board/`](../sensor_board/) and [`i2c_bus/`](../i2c_bus/): it adds the
two facts those boards leave to the firmware, **which controller a port is**
and **the address a device answers on**. Then it runs the firmware: the board's
own bare-metal firmware, in [`firmware/`](firmware/), executes in Renode
against this board, and two requirements over what it does are decided by the
run, through the commit gate.

## The program

[`sensor_node.py`](sensor_node.py) declares both vendor parts itself. The MCU's
ports each name the peripheral instance they are, and each candidate pin
carries the alternate function that routes the signal to it:

```python
i2c1 = I2CPort(peripheral="I2C1", ...)
usart2 = UARTPort(peripheral="USART2", ...)

peripherals = PinMap(
    {
        "i2c1.scl": {"PB8": AF(4), "PB6": AF(4)},
        "i2c1.sda": {"PB9": AF(4), "PB7": AF(4)},
        "usart2.tx": {"PA2": AF(7)},
        "usart2.rx": {"PA3": AF(7)},
    },
    evidence="af_table",
)
```

`evidence="af_table"` names a `Cites` on the same part: ST's DS10086 Rev 5,
table 9, the alternate function mapping. A pin map with selectors and no
citation is refused at elaboration. Because `i2c1` is one controller, the
connection `self.mcu.i2c1 >> self.env.i2c` can only lower onto I2C1's pins;
SCL cannot land on I2C1 and SDA on I2C2. Each pin connection the lowering makes
records the selector of the pin it chose and the evidence for it:

```json
"selectors": {"PIN-6093c2974cd4": {"evidence": "EVD-355c4bf2d94a", "selector": "AF4"}}
```

That is PB8, the preferred SCL candidate, at AF4. The choice of PB8/PB9 over
PB6/PB7 is a decision entity, as on `sensor_board`.

The sensor's port carries its address:

```python
i2c = I2CPort(address=0x44 * addr, ...)   # addr = UnitLiteral("1")
```

An address is a dimensionless quantity, so `address=0x44` is refused with
`UNIT-0001` naming the parameter. The HS3001 has no strap pin; Renesas gives
0x44 as the only address it answers on. The compatibility check reads it, and
the addressing rule is decided: it passes, with the message
`addresses on i2c are distinct: 0x44 (PORT-b794dc65bafa)`. The MCU's port
declares no address. It is the controller, so it is not addressed and the rule
says nothing about it.

## What the datasheets say, and what they do not

Every pad number, selector, address and level in the program is cited by table
and page from ST's DS10086 Rev 5 and Renesas's R36DS0045EU0101 Rev 1.01.
[`out/rationale.md`](out/rationale.md) lists the ten citations.

The HS3001 datasheet states no input or output logic levels for SCL and SDA, so
the program states none. The logic-level check over I2C1 is undecided, naming
the sensor's `voh_min`, rather than passed on a number nobody read.

The MCU is reduced to the pins this board uses: one of its four VDD/VSS pairs,
the two I2C1 pin pairs, PA2, PA3 and PA5. The other supply pairs and their
capacitors, the 4.7 uF bulk capacitor, VCAP_1, VDDA, VBAT, NRST and BOOT0 are
not modelled. This is a board for the checks and for running firmware against,
not one to send to fabrication. The HS3001 is modelled whole, including its VC
capacitor and the pull-ups its application circuit requires.

## The firmware, run against the board

[`firmware/src/main.c`](firmware/src/main.c) is register-level C with no vendor
HAL, running from the 16 MHz the part resets to. It prints a boot line on
USART2, asks the HS3001 for a measurement every 100 ms and prints
`temp=<degC>`, and toggles the LED on PA5 every 500 ms while readings succeed
and every 100 ms while the sensor does not answer. The ELFs in
[`firmware/elf/`](firmware/elf/) are committed, with the toolchain that built
them in [`firmware/TOOLCHAIN`](firmware/TOOLCHAIN), so nothing rebuilds them;
`make` does, byte for byte.

The board binds the firmware to the MCU and names an emulation model for each
part that has one: fang's F401 platform, and Renode's own HS3001 model. Two
questions are declared beside the requirements they serve:

- **startup**: at 25 degC from reset, the first sensor read comes within
  200 ms, the printed temperature is within 0.05 degC (the sensor's 14-bit
  quantization reads 25 degC back as 25.01), the LED rises exactly once
  between 1 s and 2 s, and no I2C1 pin is configured otherwise than the board
  requires.
- **sensor missing**: with the HS3001 absent, the LED rises at least four times
  between 1 s and 2 s.

The second question does not count reads of the sensor. An absent device has
no probe, so nothing it is asked is recorded, and a count of its reads would be
0 whatever the firmware did; a plan refuses a read or write match over a device
its fault removes, rather than letting `== 0` pass by construction.

Each compiles into a plan whose every bus, pin, alternate function and address
comes from this graph, and nowhere else: I2C1 from the port, PB8 and PB9 at AF4
and open drain from the lowered connections, 0x44 from the sensor's port, PA5
from the status signal's connection. The pull-ups and the LED's resistor share
nets with pins both questions touch, and the console header shares USART2's,
which only startup reads. None has an emulation model, so each question names
the ones it touches as abstracted, the console header in startup alone, and
the evidence lists them as coverage gaps.

`fang verify` answers both, and both pass: the firmware reads the sensor at
40 ms, prints 25.01 degC, blinks once in that second and sets I2C1's pins up
right; with the sensor gone it blinks five times. Three deliberately broken
builds sit beside the good one, and the suite runs each against the board: the
wrong address fails the first read, which is observed not to happen before the
run ends; push-pull I2C pins fail the pin check while every transaction
succeeds, because Renode does not route I2C through the pins; no timeout hangs
when the sensor is missing. Moving the LED to PA6 on the board, with the
firmware unchanged, fails the blink count.

What the run does not show is listed with it: the clock tree, I2C DMA and
timing, acknowledgement beyond an absent device, the sensor's conversion time.
Nor does the missing-sensor run show how often the firmware asks for a sensor
that is not there, since an absent device records nothing. A pass is a finding
on models tested in emulation, at confidence 0.8. It is not the board working.

## What comes out

11 parts, 9 nets, 142 entities, 17 checks. None failed, **nine undecided**.

One is the sensor's logic levels, above. Two are the console. The header passes
USART2 through to a serial adapter, and the `vih_min` and `voh_min` on the far
side of it are the adapter's. The header is this board's; the adapter is not,
and its levels are not known. The other six are the constraints over what the
firmware does, undecided until a run measures it.

- [`out/sensor_node.net`](out/sensor_node.net), [`out/netlist.txt`](out/netlist.txt)
- [`out/checks.txt`](out/checks.txt): 17 checks, nine of them undecided
- [`out/verification.txt`](out/verification.txt): what `fang verify` found, both
  questions passing
- [`out/renode/`](out/renode/): each question's plan, Renode platform
  description and script
- [`out/rationale.md`](out/rationale.md): the two requirements, the four
  lowering decisions and the datasheet citations
- [`out/graph.txt`](out/graph.txt): 142 entities

![the interfaces view](out/views/interfaces.svg)

The MCU's three links: I2C1 to the sensor, USART2 to the console header, and
the status signal to the LED's series resistor.

![the power view](out/views/power.svg)

The rail from the header to both parts and the pull-ups, with each part's
decoupling hung off its own supply pins. The VC capacitor joins the sensor's VC
pin to ground and touches no supply pin, so this view leaves it below the rule.

## Running it

```bash
fang check   examples/sensor_node/sensor_node.py
fang netlist examples/sensor_node/sensor_node.py
fang view    examples/sensor_node/sensor_node.py interfaces -o interfaces.svg
fang verify  examples/sensor_node/sensor_node.py    # needs renode 1.17.0
fang emulate examples/sensor_node/sensor_node.py --bundle-only -o bundles
make -C examples/sensor_node/firmware               # needs arm-none-eabi-gcc
```
