"""Where the potentials in problem_1.py came from.

    python examples/jee_advanced/problem_1/solve.py

The graph is elaborated, `fang.simulation` compiles a plan and lowers it to
SPICE, and ngspice solves the operating point. Nothing here re-implements a
circuit solver. Every device and node in the deck is written by
`lower_to_spice`; all this adds is the control block that makes ngspice print
the operating point rather than leave it in a raw file. The currents are read
back through `_is_ground`, the same rule the lowering numbered the nodes by,
so the two cannot disagree about which net is which.

This is a script rather than `fang sim` for one reason. GND1 marks a node and
is not a device, so it carries no simulation model, and a plan that reaches a
component with no model is rejected rather than run with a stand-in. Naming it
as abstracted is what lets the plan compile, and the plan then records the
abstraction as an assumption. `fang sim` has no flag for that.
"""

from __future__ import annotations

import re
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# examples/<group>/<problem>/ up to the checkout, so this runs from anywhere
# and against any interpreter, installed fang or not.
REPO = ROOT.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fang.cli import load_system
from fang.elaborate import elaborate
from fang.entities import Component
from fang.netlist import compile_netlist
from fang.simulation import (
    BackendUnavailable,
    NgspiceBackend,
    OperatingPoint,
    _is_ground,
    compile_plan,
    lower_to_spice,
)

#: ngspice prints an operating point in batch mode only when asked to; the
#: analysis directive alone leaves the numbers in the raw file.
CONTROL = ".control\nop\nprint all\n.endc\n.end"

NODE = re.compile(r"^[vV]\((\d+)\)\s*=\s*([-+0-9.eE]+)$")

QUESTION = "JEE (Advanced) 2022, Paper 1, question 1: which statements are correct?"

#: What the paper asks, the part in the program that answers it, and the
#: magnitude the paper claims. Only the paper knows what it asked, so this is
#: the one table the script states rather than derives.
CLAIMS = (
    ("(A) the current through R1 is 7.2 A", "r1", "7.2"),
    ("(B) the current through R2 is 1.2 A", "r2", "1.2"),
    ("(C) the current through R3 is 4.8 A", "r3", "4.8"),
    ("(D) the current through R5 is 2.4 A", "r5", "2.4"),
)


def verdict(held, solved) -> str:
    correct = [c[0][1] for c, ok in zip(CLAIMS, held) if ok]
    return (
        f"ANSWER: {len(correct)} of {len(CLAIMS)} statements hold"
        + (f" \u2014 {', '.join(correct)}." if correct else ".")
    )


def _name_of(snapshot, designators) -> dict:
    """Each component's designator against the name it has in the program.

    `R5` is what the netlist calls it; `r5` is what the paper calls it and what
    a reader of the program can find. Both are printed, because the answer has
    to be readable without holding the mapping in your head.
    """
    out = {}
    for entity in snapshot.entities.values():
        if isinstance(entity, Component) and entity.id in designators:
            path = str(entity.identity.path)
            out[designators[entity.id]] = path.split(".")[-1] if path else ""
    return out


def report(snapshot, netlist, potential, node_of) -> int:
    """Print the potentials, the currents, and the answer to the question."""
    designators = {c.entity_id: c.designator for c in netlist.components}
    named = _name_of(snapshot, designators)

    print("\n--- node potentials, against the reference ---")
    for net in netlist.nets:
        first = net.nodes[0]
        number = node_of[(first.designator, first.pin)]
        if number in potential:
            print(f"  {net.name:<28} {potential[number]:>10} V")

    print("\n--- the potentials the program claims, which these are ---")
    for entity in snapshot.entities.values():
        if entity.kind != "block":
            continue
        for key, value in sorted(entity.parameters.items()):
            if key.startswith("v_"):
                print(f"  {key:<22} {str(value.quantity):>12}")

    solved = {}
    print("\n--- branch currents ---")
    for component in netlist.components:
        if not component.designator.startswith("R"):
            continue
        one = potential[node_of[(component.designator, "1")]]
        two = potential[node_of[(component.designator, "2")]]
        ohms = Decimal(component.value.split()[0])
        current = abs((one - two) / ohms)
        solved[named[component.designator]] = current
        print(
            f"  {named[component.designator]:<22} {component.designator:<5}"
            f"{component.value:>9}  {current} A"
        )

    print(f"\n--- {QUESTION} ---")
    held = []
    for label, part, claimed in CLAIMS:
        got = solved[part]
        ok = got == Decimal(claimed)
        held.append(ok)
        print(
            f"  {'CORRECT' if ok else 'WRONG':<8} {label:<46} "
            f"({part} = {got} A)"
        )
    print(f"\n{verdict(held, solved)}")
    return 0 if all(held) else 1


def main() -> int:
    result = elaborate(load_system(ROOT / "problem_1.py"), project_id="PRJ-EXAMPLES")
    if not result.ok:
        for diagnostic in result.diagnostics:
            print(diagnostic.message, file=sys.stderr)
        return 1

    netlist = compile_netlist(result.snapshot, traits=result.traits)
    marker = next(c for c in netlist.components if c.designator == "GND1")

    plan = compile_plan(
        result.snapshot,
        analysis=OperatingPoint(),
        traits=result.traits,
        abstracted=[marker.entity_id],
    )
    deck = lower_to_spice(
        result.snapshot, plan, traits=result.traits, title="problem_1"
    )

    deck = deck.replace(".end", CONTROL)
    print("--- the deck fang lowered ---")
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

    # The node numbering fang used, rebuilt from the netlist it lowered.
    node_of = {}
    for index, net in enumerate(netlist.nets, start=1):
        number = "0" if _is_ground(net.name) else str(index)
        for node in net.nodes:
            node_of[(node.designator, node.pin)] = number

    potential = {"0": Decimal(0)}
    for line in raw.stdout.splitlines():
        match = NODE.match(line.strip())
        if match:
            potential[match.group(1)] = Decimal(match.group(2))

    print(
        f"\n--- solved by {raw.backend}, exit status {raw.exit_status} ---"
    )
    return report(result.snapshot, netlist, potential, node_of)


if __name__ == "__main__":
    raise SystemExit(main())
