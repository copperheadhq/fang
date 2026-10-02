# Tasks: MCU Parts — Peripheral Instances, Selectors and Bus Addresses

Implements copperhead RFC 12 version 1.3, Sections 7.3 and 7.4, and RFC 3
version 1.5, Section 9.3
([copperheadhq/copperhead-rfcs#6](https://github.com/copperheadhq/copperhead-rfcs/pull/6)).

## 1. Diagnostics and records

- [x] 1.1 Allocate the two `IFACE` codes named in design.md with `_allocate` at
      the bottom of the `IFACE` block; verify the registry tests pass and no
      code was reused.
- [x] 1.2 Add optional `peripheral` and `address_strap` to `Port` and optional
      `selectors` to `Connection`, each omitted from `as_dict()` when absent;
      verify every example's committed outputs still match before any program
      is edited.
- [x] 1.3 Move `SCHEMA_VERSION` to 1.2; verify the serialization tests pass and
      the examples suite still matches with the hash normalized.

## 2. Peripheral instances and selectors

- [x] 2.1 Give `InterfacePort` a `peripheral` keyword consumed before the
      parameter catch-all, and elaborate it onto the `Port` entity; verify a
      port declared as `I2C1` names it in the snapshot and that `peripheral`
      never appears among the port's parameters.
- [x] 2.2 Add `Selector` and `AF`, and let `PinMap` take a candidate-to-selector
      mapping and an `evidence` name; keep the list form; verify both forms
      give the same candidates in the same order.
- [x] 2.3 Refuse at elaboration a `PinMap` with selectors that names no
      evidence, or names one the part does not declare; verify the diagnostic
      names the part.
- [x] 2.4 Carry the chosen pin's selector and evidence id onto the `Connection`
      the lowering emits; verify a lowered `i2c1.scl` connection records `AF4`
      for the MCU's pin and the evidence id, and that a part without selectors
      lowers byte-identically to before.
- [x] 2.5 Verify that with two I2C ports on one part, a connection to one of
      them assigns only that port's candidates.

## 3. Addresses

- [ ] 3.1 Declare `address` with unit `1` on the I2C interface, and refuse a
      bare integer for it with `UNIT_DIMENSION_MISMATCH` naming the parameter;
      verify `0x44 * addr` elaborates to an explicit value and `0x44` is
      refused.
- [ ] 3.2 Add `Strap(pin, {device pin: address})`, resolve its pin names to pin
      identifiers at elaboration and store it as `address_strap`, refusing a
      name the part does not have; verify the stored strap and the refusal.
- [ ] 3.3 Add `resolve_address(snapshot, port)` over the inferred netlist,
      returning a known address, or an unknown one whose reason names the
      strap pin (and both pins when two share its net); verify ground, supply,
      bus-signal, floating and ambiguous straps.
- [ ] 3.4 Make the addressing rule in `_check_protocol` read
      `resolve_address` for every participant, fail duplicates naming both
      ports, return undecided naming the strap pin for an unresolved one, and
      skip ports with no address; verify each scenario of the delta spec's
      address requirement in `tests/test_compatibility.py`.

## 4. The example

- [ ] 4.1 Write `STM32F401RE` in `examples/sensor_node/`: vendor names and
      LQFP64 pad numbers from ST's STM32F401xD/xE datasheet, `i2c1` (I2C1;
      PB8/PB9 then PB6/PB7, AF4), `usart2` (USART2; PA2/PA3, AF7), a `status`
      signal on PA5, power pins, a `Cites` for the alternate-function table
      and one for the pinout, and its vendor identity through `select`;
      verify every selector and pad number against the cited tables.
- [ ] 4.2 Write `HS3001` with its fixed address 0x44 cited from Renesas's HS300x
      datasheet, and its pins from the same document; leave any threshold not
      read off the datasheet unknown or as an `Assumes`.
- [ ] 4.3 Write the `SensorNode` system — MCU, sensor on I2C1 with pull-ups,
      decoupling, LED and series resistor on PA5, console header on USART2,
      power header — and its README; verify it elaborates, that the
      compatibility check decides the addressing rule, and that the lowered
      I2C connections carry AF4.
- [ ] 4.4 Run `python examples/regenerate.py sensor_node`; verify
      `tests/test_examples.py` discovers and passes the new example and that no
      other example's outputs changed beyond their snapshot hash.

## 5. Documents

- [ ] 5.1 Document `peripheral`, selectors, `AF`, `Strap` and addressing on the
      interfaces reference page; add the example to `examples/README.md`;
      update `CLAUDE.md` and `CHANGELOG.md`; verify internal links resolve and
      quoted counts match the tree.
- [ ] 5.2 Quote the requirement names in each touched module's docstring;
      verify `openspec validate fang-mcu-parts --strict` and the whole suite
      pass.
