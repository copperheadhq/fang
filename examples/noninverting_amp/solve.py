"""Where the numbers in this example's document came from.

    python examples/noninverting_amp/solve.py

The two answers are claims about a band, so the check that earns them is a
frequency sweep. The graph is elaborated, `fang.simulation` compiles an a.c.
plan and lowers it to SPICE, and ngspice runs it. Nothing here re-implements a
circuit solver, and nothing here re-derives which net is which: the node
numbers come from `spice_nodes`, the same function the deck was written with,
so the script and the deck cannot disagree.

Three parts carry no simulation model and are named as abstracted, which is
what lets the plan compile and what puts each one in the plan's own
assumptions: `GND1` marks a node, `TP1` marks a terminal, and `U1` is an ideal
op amp that no model was ever written for. A plan that reached a component with
no model would be rejected rather than run with a stand-in.

Two cards the deck does not carry are added here, and they are the script's,
not fang's:

    V1  the source. The figure draws a signal arriving and no generator, so
        there is nothing in the graph to lower into one.
    E1  a voltage-controlled source with a gain of a million, standing in for
        the op amp the plan abstracted. An ideal op amp is what the answers
        assume, so it is what gets simulated.

The analysis is still the plan's: the `.ac` line is the one `lower_to_spice`
wrote, and the control block runs it rather than asking for a second one.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT.parent.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent.parent))

from fang.cli import load_system
from fang.elaborate import elaborate
from fang.netlist import compile_netlist
from fang.simulation import (
    ACSweep,
    BackendUnavailable,
    NgspiceBackend,
    compile_plan,
    lower_to_spice,
    spice_nodes,
)

#: The parts with no simulation model. Naming them is what lets the plan
#: compile; the plan then records each one as an assumption.
ABSTRACTED = ("U1", "TP1", "GND1")

#: What to ask of the run, and what the program claims the answer is. `meas`
#: reads one frequency out of the sweep, so each row is one number against one
#: claim.
MEASUREMENTS = (
    ("gain_1k", "gain", 1_000, "Av at 1 kHz", "16 claimed"),
    ("gain_10k", "gain", 10_000, "Av at 10 kHz", ""),
    ("zin_1k", "zin", 1_000, "Zin at 1 kHz", "68750 claimed"),
    ("zin_100k", "zin", 100_000, "Zin at 100 kHz", ""),
)

MEASURED = re.compile(r"^(\w+)\s*=\s*([-+0-9.eE]+)$")


def control(nodes) -> str:
    """The control block: run the plan's analysis, then read four numbers.

    `run` rather than a second `ac` line, so what is measured is the sweep the
    plan asked for. ngspice measures a named vector rather than an expression,
    so the gain and the impedance are named first.
    """
    output, load, drive = nodes["out"], nodes["load"], "v1"
    lines = [
        ".control",
        "run",
        f"let gain = mag(v({output}))",
        f"let load = mag(v({load}))",
        f"let zin = mag(1/i({drive}))",
    ]
    for name, vector, at, _, _ in MEASUREMENTS:
        lines.append(f"meas ac {name} find {vector} at={at}")
    lines.append(".endc")
    return "\n".join(lines) + "\n.end\n"


def main() -> int:
    result = elaborate(
        load_system(ROOT / "noninverting_amp.py"), project_id="PRJ-EXAMPLES"
    )
    if not result.ok:
        for diagnostic in result.diagnostics:
            print(diagnostic.message, file=sys.stderr)
        return 1

    netlist = compile_netlist(result.snapshot, traits=result.traits)
    designator = {component.designator: component for component in netlist.components}

    plan = compile_plan(
        result.snapshot,
        analysis=ACSweep(variation="dec", points=20, start="10", stop="1meg"),
        traits=result.traits,
        abstracted=[designator[name].entity_id for name in ABSTRACTED],
    )
    deck = lower_to_spice(
        result.snapshot, plan, traits=result.traits, title="noninverting_amp"
    )

    # The numbering the deck was written with, asked for rather than rebuilt.
    node = spice_nodes(result.snapshot, netlist)
    nodes = {
        "in": node[("TP1", "1")],
        "plus": node[("U1", "IN+")],
        "minus": node[("U1", "IN-")],
        "out": node[("U1", "OUT")],
        "load": node[("R5", "1")],
    }

    added = (
        f"V1 {nodes['in']} 0 AC 1\n"
        f"E1 {nodes['out']} 0 {nodes['plus']} {nodes['minus']} 1e6\n"
    )
    deck = deck.replace(".end\n", added + control(nodes))

    print("--- the deck fang lowered, and the two cards this script adds ---")
    print(deck)
    for assumption in plan.assumptions:
        print(f"assumption: {assumption}")
    for gap in plan.coverage_gaps:
        print(f"coverage gap: {gap}")

    backend = NgspiceBackend()
    # The backend is reached across a process boundary, and the deck it reads is
    # a copy: the project stays unreachable to it.
    try:
        with tempfile.TemporaryDirectory() as scratch:
            raw = backend.run(deck, workspace=Path(scratch))
    except BackendUnavailable as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1

    measured = {}
    for line in raw.stdout.splitlines():
        match = MEASURED.match(line.strip())
        if match:
            measured[match.group(1)] = float(match.group(2))

    print(f"\n--- solved by {raw.version}, exit status {raw.exit_status} ---")
    for name, _, _, label, claim in MEASUREMENTS:
        if name not in measured:
            print(f"  {label:18} not measured")
            continue
        value = measured[name]
        shown = f"{value:,.2f}" if value < 100 else f"{value:,.0f} Ohm"
        print(f"  {label:18} {shown:>14}   {claim}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
