---
title: Firmware against the board
description: Why emulation is a verification question, and why the board, not a second wiring description, decides what the emulator sees.
sidebar:
  order: 8
  attrs:
    data-icon: puzzle
---

A board can record which pin of a microcontroller carries SCL, and which of its
controllers that pin belongs to, and still say nothing about the firmware that
will drive it. The defects that live between the two, the wrong address, the
wrong pin, a missing timeout, are the ones found at bring-up, on a fabricated
board. Emulation asks about them earlier, and asks in the board's own terms.

## The board is the wiring

Nothing describes the emulated hardware but the graph. The plan reads the bus
controller from the port, the pins and their alternate functions from the
lowered connections, the address from the sensor's port, and the pin the LED
hangs off from the connection the program made. There is no second, hand-kept
wiring list for the emulator to drift from: change the board and the plan
changes with it.

## A question, not a report

An emulation is a question in the same sense a circuit simulation is (see
[Verification](/concepts/verification/)): declared beside the requirement it
serves, compiled into a plan, run by a tool, and answered by measurements that re-enter the graph through the commit gate. The
constraint the requirement states is decided by the constraint check the gate
already runs. A measured value that breaks a hard constraint never reaches the
head; the run is recorded as a failed verification, with the number that
failed it.

Because the question is in the graph, so is everything that could turn a
failure into a pass. Widening an assertion window is a transaction with a
diff and provenance, decided by the same policy as any other change.

## Observed, not reported

The emulator's probes record what a device was asked and answered, what a pin
did, and what a UART carried, each at its virtual time. A line the firmware
prints is its report of itself, and is recorded as one; it does not stand in
for what the bus saw.

## Honest about what was not seen

Three rules carry the kernel's treatment of unknowns into a run. An event
observed not to occur before a completed run's end is a measurement, the
half-open range after the end, and decides a deadline; a run that ended early
decides nothing. A model that warns of something it does not cover withdraws
the measures that rest on it. And where the emulator does not route a
peripheral through its pins' configuration, the configuration is measured from
what the firmware wrote, instead of trusted.

A measure that could only ever read one way is refused before anything runs:
a count over an empty window, a read of a device the question has removed, a
pin configuration over a port that carries no bus. Each would pass its
constraint by construction, which is a pass nobody observed.

## A finding, not a proof

Every run lists what its models do not cover, and its confidence is bounded by
how far those models have been qualified. Emulation narrows what first-spin
validation has to find; it does not replace it.

## Where it goes next

The bundle a run executes (the plan, the platform description, the script,
the probes, the firmware and a manifest of digests) is a function of the
question and the firmware alone. A hosted runner can execute the same bundle
in a sandbox, and fang reads its events with the same measures, so the verdict
is the same code whichever machine ran it.
