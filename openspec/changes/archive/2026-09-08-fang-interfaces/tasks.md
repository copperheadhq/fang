# Tasks: Typed Interfaces And Pin Lowering

## 1. Interface model

- [x] 1.1 Implement `InterfaceType` with signals, roles, directions, and required flags.
- [x] 1.2 Implement interface electrical parameters and their declared units.
- [x] 1.3 Implement the catalogue covering all seventeen named interfaces.
- [x] 1.4 Allow a project to register its own interface type.
- [x] 1.5 Implement `InterfacePort` as a multi-signal surface in the language.

## 2. Pin model

- [x] 2.1 Implement `Pin` with a canonical role and the preserved vendor name.
- [x] 2.2 Implement `PinMap` declaring candidate pins per interface signal.
- [x] 2.3 Emit pin entities owned by their part during elaboration.

## 3. Lowering

- [x] 3.1 Implement deterministic assignment over the declared candidate order,
      which is the engineer's stated preference and is reproducible.
- [x] 3.2 Prevent one pin carrying two signals within a lowering.
- [x] 3.3 Record a decision entity where a choice existed, naming rejected alternatives.
- [x] 3.4 Emit pin connections with provenance naming the interface connection.
- [x] 3.5 Fail with `IFACE-0001` on an unsatisfiable signal, producing no partial mapping.
- [x] 3.6 Fail with `IFACE-0002` on a membership disagreement.
- [x] 3.7 Prove the lowering is re-derivable from the same graph state.

## 4. Compatibility

- [x] 4.1 Implement logic-level margin checks over VOH, VIH, VOL, and VIL.
- [x] 4.2 Implement current capability against demand.
- [x] 4.3 Implement voltage-domain agreement across every bus participant.
- [x] 4.4 Implement pull-up supply validity and open-drain requirements.
- [x] 4.5 Implement protocol, rate, and addressing agreement.
- [x] 4.6 Return undecided naming the missing input rather than passing by default.
- [x] 4.7 Cite the evidence entity behind a datasheet-sourced input.
- [x] 4.8 Register compatibility as a check class the commit gate can require.

## 5. Tests

- [x] 5.1 Cover every scenario in this change's delta spec.
- [x] 5.2 Add an end-to-end test lowering an I2C link between two parts.
