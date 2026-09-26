"""What every circuit in the handbook shares: its parts, and the bench that runs it.

SBOA092B draws its circuits from a handful of things: an operational
amplifier, a terminal where a signal arrives or leaves, the ground rail, and
now and then a diode, a potentiometer, a switch, a meter or a standard cell.
They are declared once, here, so seventy programs do not each invent their
own op amp.

The bench is how a program is simulated. `fang.simulation` compiles a plan and
lowers the snapshot to SPICE, and that lowering writes the devices SPICE knows
natively: resistors, capacitors, inductors and independent sources. Every
other part is named as abstracted, which puts it in the plan's own
assumptions, and then writes its own cards: the op amp a macro-model, a diode
its device and model, a potentiometer the two resistors either side of its
wiper. Nothing re-derives which net is which; node numbers come from
`spice_nodes`, the function the deck was written with.

The drive is the bench's too. The handbook draws E_I as a pair of terminals
and no generator, so there is nothing in the graph to lower into one, and a
run says what it applies to which terminal.

A program declares its bench as a module-level ``BENCH``. Each run is one deck
and one ngspice invocation, and every claim it checks names a measurement and
either a number or a parameter of the system, so a claim the program makes is
checked against the value the graph holds rather than a copy of it.
`examples/regenerate.py` writes what the bench measured into the example's
``out/``, beside the decks it ran.
"""

from __future__ import annotations

import math
import re
import sys
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping, Sequence

from fang.constraints import Arithmetic, Comparison, Literal, Logical, Node
from fang.entities import Component
from fang.interfaces import AnalogIn, AnalogOut, Pin, PinMap
from fang.lang import Electrical, MHz, Parameter, ParameterRef, Part, UnitLiteral, V
from fang.netlist import compile_netlist
from fang.parts import Diode, TestPoint, TwoPin
from fang.simulation import (
    Analysis,
    NgspiceBackend,
    compile_plan,
    lower_to_spice,
    spice_nodes,
)

#: A dimensionless literal, so a gain is a quantity like every other number.
ratio = UnitLiteral("1")


#: Written out to the precision a Decimal keeps: constraints are evaluated in
#: decimal, and a binary float never reaches a quantity.
TWO_PI = ratio("6.283185307179586")


# --------------------------------------------------------------------------
# Writing the expression tree out
# --------------------------------------------------------------------------
#
# A parameter reference builds a node from one operator, and a node is not
# itself an operand of Python's operators, so anything nested is written out
# with these. Every node checks its own dimensions as it is constructed, so a
# gain that comes out in ohms is rejected at the line that wrote it.


def node(value) -> Node:
    if isinstance(value, Node):
        return value
    if isinstance(value, ParameterRef):
        return value._node()
    return Literal.of(value)


def total(*terms) -> Arithmetic:
    """The sum of the terms. Dimensions must agree."""
    return Arithmetic("add", tuple(node(term) for term in terms))


def minus(left, right) -> Arithmetic:
    return Arithmetic("sub", (node(left), node(right)))


def product(*terms) -> Arithmetic:
    return Arithmetic("mul", tuple(node(term) for term in terms))


def over(numerator, denominator) -> Arithmetic:
    return Arithmetic("div", (node(numerator), node(denominator)))


def negative(value) -> Arithmetic:
    return Arithmetic("neg", (node(value),))


def parallel(one, other) -> Arithmetic:
    """Two impedances side by side: the product over the sum."""
    return over(product(one, other), total(one, other))


def corner(resistance, capacitance) -> Arithmetic:
    """1 / (2 pi R C): where an RC pair turns, in hertz."""
    return over(1 * ratio, product(TWO_PI, resistance, capacitance))


def equals(left, right) -> Comparison:
    return Comparison("eq", (node(left), node(right)))


def at_most(left, right) -> Comparison:
    return Comparison("le", (node(left), node(right)))


def at_least(left, right) -> Comparison:
    return Comparison("ge", (node(left), node(right)))


def within(value, target, fraction) -> Logical:
    """`value` is within a fraction of `target`, either side of it.

    For a claim the handbook rounds: 1/(2 pi 100k 1u) is 1.59 Hz, which it
    prints as 1.6, and an exact equality would reject its own figure.
    """
    # The band is a width, so it is taken from the target's magnitude: a band
    # built from a negative gain would put the upper bound below the lower.
    band = product(Arithmetic("abs", (node(target),)), fraction * ratio)
    return Logical(
        "and",
        (
            at_least(value, minus(target, band)),
            at_most(value, total(target, band)),
        ),
    )


# --------------------------------------------------------------------------
# The parts
# --------------------------------------------------------------------------


class Terminal(TestPoint):
    """One of the open circles the handbook draws: where a signal enters or leaves.

    It marks a node and adds nothing to it. A bench drives it, or measures it.
    """


class Ground(Part):
    """The rail every voltage in a figure is measured against.

    One terminal whose role is ground, which is how the lowering finds node 0:
    from the graph, not from a net's name.
    """

    designator_prefix = "GND"

    node = Electrical()
    PIN1 = Pin("1", role="ground", number="1")
    pinmap = PinMap({"node.line": "1"})


class OpAmp(Part):
    """An operational amplifier, as the handbook treats one.

    Two inputs and an output, and no supply pins, because the figures draw
    none: the rails show up only as the swing the output cannot pass. The pin
    numbers are the single-op-amp 8-pin pinout, 2, 3 and 6. Nothing here names
    a vendor. Where the handbook names a part (TLC265x, OPA277) the program
    says so in prose, and the model parameters are what reach the simulator.

    The defaults are an op amp close enough to ideal that the handbook's ideal
    algebra is what a run measures: 120 dB of open-loop gain, 10 MHz of
    gain-bandwidth, no offset, and the +/-13.5 V swing the handbook assumes
    on +/-15 V supplies. A program that needs a real part's limits sets them.
    """

    designator_prefix = "U"

    inverting = AnalogIn()
    non_inverting = AnalogIn()
    output = AnalogOut()

    IN_MINUS = Pin("IN-", role="analog", number="2")
    IN_PLUS = Pin("IN+", role="analog", number="3")
    OUT = Pin("OUT", role="analog", number="6")

    pinmap = PinMap(
        {
            "inverting.signal": "IN-",
            "non_inverting.signal": "IN+",
            "output.signal": "OUT",
        }
    )

    open_loop_gain = Parameter("1", default=1000000 * ratio)
    gain_bandwidth = Parameter("Hz", default=10 * MHz)
    output_high = Parameter("V", default=13.5 * V)
    output_low = Parameter("V", default=-13.5 * V)
    input_offset = Parameter("V", default=0 * V)

    def spice(self, ref: str, node: Callable[[str], str], value: Callable[[str], float]):
        return (
            [
                f"X{ref} {node('IN+')} {node('IN-')} {node('OUT')} HB_OPAMP "
                f"A={_g(value('open_loop_gain'))} GBW={_g(value('gain_bandwidth'))} "
                f"VOH={_g(value('output_high'))} VOL={_g(value('output_low'))} "
                f"VOS={_g(value('input_offset'))}"
            ],
            {"HB_OPAMP": OPAMP_MODEL},
        )

    def describe(self, value: Callable[[str], float]) -> str:
        return (
            f"op amp macro-model: {_g(value('open_loop_gain'))} open-loop gain, "
            f"{_eng(value('gain_bandwidth'), 'Hz')} gain-bandwidth, output "
            f"{_eng(value('output_low'), 'V')} to {_eng(value('output_high'), 'V')}, "
            f"offset {_eng(value('input_offset'), 'V')}"
        )


class DifferentialOpAmp(OpAmp):
    """An op amp with two outputs, whose difference is what the loop sets.

    The handbook's balanced-output figures (pages 69 and 75) use one. The
    output that feeds back to the inverting input is OUT+, the one that falls
    when that input rises. Where the two outputs sit together is set inside the
    part and not by the loop, as the handbook says; the model holds that
    common level at ground.
    """

    output_minus = AnalogOut()
    OUT = Pin("OUT+", role="analog", number="6")
    OUT_MINUS = Pin("OUT-", role="analog", number="5")

    pinmap = PinMap(
        {
            "inverting.signal": "IN-",
            "non_inverting.signal": "IN+",
            "output.signal": "OUT+",
            "output_minus.signal": "OUT-",
        }
    )

    def spice(self, ref, node, value):
        return (
            [
                f"X{ref} {node('IN+')} {node('IN-')} {node('OUT+')} {node('OUT-')} "
                f"HB_FDA A={_g(value('open_loop_gain'))} "
                f"GBW={_g(value('gain_bandwidth'))} VOH={_g(value('output_high'))} "
                f"VOL={_g(value('output_low'))} VOS={_g(value('input_offset'))}"
            ],
            {"HB_OPAMP": OPAMP_MODEL, "HB_FDA": FDA_MODEL},
        )


class SignalDiode(Diode):
    """A small-signal silicon diode: a 1N4148, which the handbook names on page 47."""

    def spice(self, ref, node, value):
        return [f"D{ref} {node('A')} {node('K')} D1N4148"], {"D1N4148": DIODE_MODEL}

    def describe(self, value) -> str:
        return "1N4148 diode model"


class Zener(Diode):
    """A zener diode, named by the voltage it breaks down at."""

    def spice(self, ref, node, value):
        name = f"DZ_{ref}"
        model = (
            f".model {name} D(IS=1e-12 N=1.5 RS=2 BV={_g(value('reverse_voltage'))} "
            "IBV=5m NBV=1.5)"
        )
        return [f"D{ref} {node('A')} {node('K')} {name}"], {name: model}

    def describe(self, value) -> str:
        return f"zener model breaking down at {_eng(value('reverse_voltage'), 'V')}"


class Potentiometer(Part):
    """A potentiometer: a resistance between its ends, and a wiper that divides it.

    `setting` is how far along the travel the wiper sits, 0 at pin 1 and 1 at
    pin 3. A rheostat is a potentiometer with its wiper tied to one end, and the
    program draws it that way.
    """

    designator_prefix = "RV"

    end_a = Electrical()
    wiper = Electrical()
    end_b = Electrical()
    bridges = (("end_a", "wiper"), ("wiper", "end_b"))

    PIN1 = Pin("1", role="unknown", number="1")
    PIN2 = Pin("2", role="unknown", number="2")
    PIN3 = Pin("3", role="unknown", number="3")
    pinmap = PinMap({"end_a.line": "1", "wiper.line": "2", "end_b.line": "3"})

    resistance = Parameter("Ohm")
    setting = Parameter("1", default=Decimal("0.5") * ratio)

    def spice(self, ref, node, value):
        total, setting = value("resistance"), value("setting")
        # A wiper at the very end still leaves a contact resistance, and SPICE
        # refuses a resistor of zero.
        upper = max(total * setting, 1e-3)
        lower = max(total * (1 - setting), 1e-3)
        return (
            [
                f"R{ref}_A {node('1')} {node('2')} {_g(upper)}",
                f"R{ref}_B {node('2')} {node('3')} {_g(lower)}",
            ],
            {},
        )

    def describe(self, value) -> str:
        return (
            f"{_eng(value('resistance'), 'Ohm')} split at the wiper, set to "
            f"{_g(value('setting'))} of its travel"
        )


class Switch(TwoPin):
    """A single-pole switch. Whether it is open or closed is the run's to say."""

    designator_prefix = "SW"

    def spice(self, ref, node, value, state: str = "open"):
        control = {"open": "DC 0", "closed": "DC 1"}.get(state, state)
        return (
            [
                f"S{ref} {node('1')} {node('2')} ctl_{ref} 0 HB_SWITCH",
                f"V{ref}_CTL ctl_{ref} 0 {control}",
            ],
            {"HB_SWITCH": SWITCH_MODEL},
        )

    def describe(self, value) -> str:
        return "switch: 1 Ohm closed, 1 TOhm open"


class Meter(TwoPin):
    """A moving-coil meter: a resistance, and the current through it is the reading.

    The bench puts a zero-volt source in series, named V<ref>_SENSE, so a
    measurement reads the reading as `i(v<ref>_sense)`.
    """

    designator_prefix = "M"
    resistance = Parameter("Ohm")

    def spice(self, ref, node, value):
        return (
            [
                f"R{ref} {node('1')} sense_{ref} {_g(value('resistance'))}",
                f"V{ref}_SENSE sense_{ref} {node('2')} DC 0",
            ],
            {},
        )

    def describe(self, value) -> str:
        return f"meter movement of {_eng(value('resistance'), 'Ohm')}"


class Cell(TwoPin):
    """A source of EMF the figure draws: a standard cell, a reference, a supply.

    Its prefix is V, so it is a device SPICE knows and fang's own lowering
    writes it; the bench adds nothing for it. Pin + is the positive terminal.
    """

    designator_prefix = "V"
    voltage = Parameter("V")

    PIN1 = Pin("+", role="unknown", number="1")
    PIN2 = Pin("-", role="unknown", number="2")
    pinmap = PinMap({"p1.line": "+", "p2.line": "-"})


# --------------------------------------------------------------------------
# The models the bench writes
# --------------------------------------------------------------------------

#: One pole, a clamped output and an input offset. A transconductance drives an
#: RC whose DC gain is A and whose unity-gain frequency is GBW; the clamp holds
#: that node inside the swing, so an output that saturates comes back without
#: first unwinding a thousand volts of integrator. The output itself is ideal.
OPAMP_MODEL = """\
.subckt HB_OPAMP inp inn out A=1e6 GBW=1e7 VOH=13.5 VOL=-13.5 VOS=0
VOS inp x DC {VOS}
RIN x inn 1e12
GM 0 n1 x inn 1e-3
R1 n1 0 {A*1e3}
C1 n1 0 {1e-3/(6.283185307179586*GBW)}
DH n1 h HB_CLAMP
VH h 0 DC {VOH}
DL l n1 HB_CLAMP
VL l 0 DC {VOL}
EO out 0 n1 0 1
.model HB_CLAMP D(IS=1e-15 N=0.01)
.ends HB_OPAMP"""

#: The same front end, with the output split symmetrically about ground.
FDA_MODEL = """\
.subckt HB_FDA inp inn outp outn A=1e6 GBW=1e7 VOH=13.5 VOL=-13.5 VOS=0
XHALF inp inn half HB_OPAMP A={A} GBW={GBW} VOH={VOH} VOL={VOL} VOS={VOS}
EP outp 0 half 0 0.5
EN outn 0 half 0 -0.5
.ends HB_FDA"""

DIODE_MODEL = (
    ".model D1N4148 D(IS=2.52e-9 RS=0.568 N=1.752 CJO=4e-12 M=0.4 TT=20e-9 "
    "BV=100 IBV=100e-6)"
)

SWITCH_MODEL = ".model HB_SWITCH SW(VT=0.5 VH=0.1 RON=1 ROFF=1e12)"


# --------------------------------------------------------------------------
# The bench
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """A number a run is expected to measure.

    `expected` is a number in SI units, or the name of a parameter of the
    system, in which case the value is read from the snapshot: the claim is the
    one the graph holds, not a copy of it. `within` is the tolerance, relative
    by default and absolute when `absolute` is set, because a claim that a
    number is zero cannot be held to a fraction of itself.
    """

    measure: str
    expected: float | str
    within: float = 0.01
    absolute: bool = False
    unit: str = ""
    note: str = ""


@dataclass(frozen=True)
class Run:
    """One deck and one simulator invocation.

    `drive` maps a terminal (the program's attribute name) to a SPICE source
    specification applied between it and ground; its source is named
    `VDRIVE_<terminal>`, so a measurement reads its current as
    `i(vdrive_<terminal>)`. `measure` maps a name to either a clause of
    ngspice's `meas` command (it starts with find, when, max, min, avg, rms,
    pp, integ, deriv or trig) or an expression to evaluate after the run. In both,
    `{part.PIN}` stands for the node that pin sits on. `settings` overrides a
    part's parameter for this run only, and `switches` sets each switch open,
    closed, or to a control waveform. `cards` are extra lines, for the
    occasional thing no part can say for itself, such as an initial condition.
    `units` names the unit a measurement is reported in, where no claim does.
    """

    name: str
    analysis: Analysis
    drive: Mapping[str, str] = field(default_factory=dict)
    measure: Mapping[str, str] = field(default_factory=dict)
    claims: Sequence[Claim] = ()
    settings: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    switches: Mapping[str, str] = field(default_factory=dict)
    cards: Sequence[str] = ()
    units: Mapping[str, str] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class Bench:
    """How a program is simulated: which page it is from, and its runs."""

    page: int
    title: str
    runs: Sequence[Run]

    def render(self, result, system, stem: str) -> dict[str, str]:
        """The files a bench adds to an example's out/: each deck, and the verdicts.

        Raises `BackendUnavailable` where ngspice is not installed, so a caller
        can skip rather than write a result nobody measured.
        """
        circuit = Circuit(result, system)
        files: dict[str, str] = {}
        lines = [
            f"# {stem}: SBOA092B page {self.page}, {self.title}",
            "",
            "What ngspice measured, against what the program claims. The decks",
            "it ran are beside this file, under spice/.",
            "",
        ]
        held = total = 0
        gaps: set[str] = set()
        for run in self.runs:
            outcome = run_one(run, circuit, stem)
            files[f"spice/{run.name}.cir"] = outcome.deck
            lines.extend(outcome.report)
            held += outcome.held
            total += outcome.total
            gaps.update(outcome.gaps)

        lines.append("## What the plan abstracted, and what the bench wrote for it")
        lines.append("")
        lines.append(
            "fang lowers the resistors, capacitors and cells itself. These it names"
        )
        lines.append(
            "as abstracted, which puts each in the plan's assumptions, and the bench"
        )
        lines.append("writes their cards instead:")
        lines.append("")
        lines.extend(f"  {line}" for line in circuit.described())
        lines.append("")
        if gaps:
            lines.append("Coverage the plan itself says it lacks:")
            lines.append("")
            lines.extend(f"  {gap}" for gap in sorted(gaps))
            lines.append("")
        lines.append(f"{held} of {total} claims hold.")
        files["simulation.txt"] = "\n".join(lines) + "\n"
        return files


class Circuit:
    """One elaborated program, indexed the ways a bench needs it.

    Parts by the name the program gives them, their designators, and the SPICE
    node every pin sits on, asked of `spice_nodes` rather than rebuilt.
    """

    def __init__(self, result, system) -> None:
        self.snapshot, self.traits = result.snapshot, result.traits
        netlist = compile_netlist(self.snapshot, traits=self.traits)
        self.nodes = spice_nodes(self.snapshot, netlist)
        designator_of = {c.entity_id: c.designator for c in netlist.components}

        self.parts = {
            name: value for name, value in vars(system).items() if isinstance(value, Part)
        }
        self.components: dict[str, Component] = {}
        for entity in self.snapshot.entities.values():
            if isinstance(entity, Component):
                segments = entity.identity.path.segments
                if len(segments) == 2 and segments[1].name in self.parts:
                    self.components[segments[1].name] = entity
        self.ref = {name: designator_of[c.id] for name, c in self.components.items()}
        self.label = {c.id: f"{self.ref[name]} ({name})" for name, c in self.components.items()}

    def node(self, part: str, pin: str) -> str:
        return self.nodes[(self.ref[part], pin)]

    def fill(self, text: str) -> str:
        """Put nodes where a text names `{part.PIN}`."""
        return _PLACEHOLDER.sub(lambda m: self.node(m.group(1), m.group(2)), text)

    def named(self, text: str) -> str:
        """Put designators and names where a sentence of fang's carries identifiers."""
        return _IDENTIFIER.sub(lambda m: self.label.get(m.group(0), m.group(0)), text)

    def abstracted(self) -> list[str]:
        """Every part SPICE has no native device for, in designator order."""
        return [
            name
            for name in sorted(self.components, key=lambda n: self.ref[n])
            if self.components[name].extensions.get("designator_prefix")
            not in _NATIVE
        ]

    def value_of(
        self, name: str, overrides: Mapping[str, float] = {}, asked: set | None = None
    ):
        component = self.components[name]

        def value(parameter: str) -> float:
            if asked is not None:
                asked.add(parameter)
            if parameter in overrides:
                return float(overrides[parameter])
            return si(component.parameters[parameter])

        return value

    def described(self) -> list[str]:
        out = []
        for name in self.abstracted():
            part = self.parts[name]
            if hasattr(part, "describe"):
                what = part.describe(self.value_of(name))
            elif isinstance(part, Ground):
                what = "the ground; its net is node 0, and it adds nothing"
            else:
                what = "a terminal; it marks a node and adds nothing"
            out.append(f"{self.ref[name]} ({name}): {what}")
        return out


@dataclass
class Outcome:
    deck: str
    report: list[str]
    held: int
    total: int
    gaps: list[str]


#: The designator prefixes SPICE has a native device for, which fang lowers.
_NATIVE = frozenset({"R", "C", "L", "V", "I"})
#: A `meas` clause, as opposed to an expression to print.
_MEAS = re.compile(r"^(find|when|max|min|avg|rms|pp|integ|deriv|trig)\b", re.IGNORECASE)
#: `{part.PIN}` in a measurement, a drive or a card.
_PLACEHOLDER = re.compile(r"\{(\w+)\.([^{}\s]+)\}")
#: A line ngspice prints for a measurement or a printed scalar. A `max` or a
#: `when` goes on to say where (`at= ...`), which is not the value. A complex
#: result prints as `re,im`, and taking its real part alone would check a
#: claim against half a number, so a value followed by a comma is not one.
_MEASURED = re.compile(r"^(\w+)\s*=\s*([^\s,]+)(,?)")
#: An entity identifier, inside a sentence fang wrote.
_IDENTIFIER = re.compile(r"\b[A-Z]{2,8}-[0-9a-f]{12,}\b")


def run_one(run: Run, circuit: Circuit, stem: str) -> Outcome:
    snapshot, traits = circuit.snapshot, circuit.traits

    # Everything that is not a device SPICE knows is abstracted, and the parts
    # that can say what they are write their own cards.
    abstracted, cards, models = [], [], {}
    asked: dict[str, set] = {}
    for name in circuit.abstracted():
        abstracted.append(circuit.components[name].id)
        part = circuit.parts[name]
        if not hasattr(part, "spice"):
            continue  # a terminal or the ground: it marks a node and adds nothing
        ref = circuit.ref[name]
        asked[name] = set()
        value = circuit.value_of(name, run.settings.get(name, {}), asked[name])
        node = lambda pin, ref=ref: circuit.nodes[(ref, pin)]
        if isinstance(part, Switch):
            written, needed = part.spice(ref, node, value, run.switches.get(name, "open"))
        else:
            written, needed = part.spice(ref, node, value)
        cards.extend(written)
        models.update(needed)

    # A setting is applied where the bench writes a part's cards, which fang's
    # own lowering does not do; one naming any other part would be dropped
    # without a word, so it is refused instead.
    for name in run.settings:
        if name not in circuit.parts or not hasattr(circuit.parts[name], "spice"):
            raise ValueError(
                f"{run.name}: settings name {name!r}, which the bench does not write; "
                "a resistor fang lowers keeps its value, so model one that changes "
                "as a Potentiometer"
            )
        # A parameter the part never reads would be ignored just as quietly.
        unread = set(run.settings[name]) - asked.get(name, set())
        if unread:
            raise ValueError(
                f"{run.name}: settings give {name} {sorted(unread)}, which its "
                f"cards never read; it reads {sorted(asked.get(name, set()))}"
            )

    plan = compile_plan(
        snapshot, analysis=run.analysis, traits=traits, abstracted=abstracted
    )
    deck = lower_to_spice(snapshot, plan, traits=traits, title=f"{stem}: {run.name}")

    added = ["* added by the bench: the drive, and the parts fang abstracted"]
    for terminal, source in sorted(run.drive.items()):
        added.append(f"VDRIVE_{terminal} {circuit.node(terminal, '1')} 0 {circuit.fill(source)}")
    added.extend(cards)
    added.extend(circuit.fill(card) for card in run.cards)
    added.extend(models[name] for name in sorted(models))

    control = [".control", "run"]
    kind = run.analysis.kind
    analysis = {"transient": "tran", "ac": "ac", "dc": "dc"}.get(kind)
    for name, text in run.measure.items():
        text = circuit.fill(text)
        if _MEAS.match(text):
            if analysis is None:
                raise ValueError(f"{run.name}: `meas` needs a sweep, not {kind}")
            control.append(f"meas {analysis} {name} {text}")
        else:
            control.append(f"let {name} = {text}")
            control.append(f"print {name}")
    control.append(".endc")

    deck = deck.replace(".end\n", "\n".join(added + control) + "\n.end\n")

    with tempfile.TemporaryDirectory() as scratch:
        raw = NgspiceBackend().run(deck, workspace=Path(scratch))

    measured: dict[str, float] = {}
    for line in raw.stdout.splitlines():
        match = _MEASURED.match(line.strip())
        if match and not match.group(3):
            try:
                number = float(match.group(2))
            except ValueError:
                continue  # not a number: it stays unmeasured
            if math.isfinite(number):
                measured[match.group(1).lower()] = number

    report = [f"## {run.name}: {_analysis(run.analysis)}", ""]
    if run.note:
        report.extend(_wrap(run.note))
        report.append("")
    for terminal, source in sorted(run.drive.items()):
        report.append(f"  drive  {terminal}: {source}")
    for name, overrides in sorted(run.settings.items()):
        for parameter, setting in sorted(overrides.items()):
            report.append(f"  set    {name}.{parameter} = {_g(float(setting))}")
    for name, state in sorted(run.switches.items()):
        report.append(f"  switch {name}: {state}")
    if run.drive or run.settings or run.switches:
        report.append("")

    held = 0
    width = max((len(name) for name in run.measure), default=0)
    claimed = {claim.measure for claim in run.claims}
    for claim in run.claims:
        got = measured.get(claim.measure.lower())
        expected = (
            system_value(snapshot, claim.expected)
            if isinstance(claim.expected, str)
            else float(claim.expected)
        )
        source = f" ({claim.expected})" if isinstance(claim.expected, str) else ""
        tolerance = (
            f"+/- {_eng(claim.within, claim.unit)}"
            if claim.absolute
            else f"+/- {_g(claim.within * 100)}%"
        )
        if got is None:
            verdict, shown = "FAILS: not measured", "-"
        else:
            limit = claim.within if claim.absolute else claim.within * abs(expected)
            verdict = "holds" if abs(got - expected) <= limit else "FAILS"
            shown = _eng(got, claim.unit)
        held += verdict == "holds"
        report.append(
            f"  {claim.measure:<{width}}  {shown:>12}   claimed "
            f"{_eng(expected, claim.unit)}{source} {tolerance}, {verdict}"
        )
        if claim.note:
            report.extend(_wrap(claim.note, indent=f"  {'':<{width}}  "))
    for name in run.measure:
        if name not in claimed:
            got = measured.get(name.lower())
            shown = _eng(got, run.units.get(name, "")) if got is not None else "-"
            report.append(f"  {name:<{width}}  {shown:>12}   not a claim")
    report.append("")

    # A plan says what it does not cover. That the bench wrote a part fang
    # abstracted is said once, beside the part; the rest is the run's own.
    gaps = [
        circuit.named(gap)
        for gap in plan.coverage_gaps
        if "is abstracted, not modelled" not in gap and "no probes were requested" not in gap
    ]
    return Outcome(deck, report, held, len(run.claims), gaps)


def _wrap(text: str, indent: str = "", width: int = 76) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent)


def si(value) -> float:
    """A value's magnitude in SI units, as the simulator wants it."""
    quantity = value.quantity
    if quantity is None:
        raise ValueError("an unknown value cannot be simulated")
    return float(quantity.value * quantity.unit.factor)


def system_value(snapshot, name: str) -> float:
    """A parameter of the system itself, read from the snapshot."""
    for entity in snapshot.entities.values():
        segments = entity.identity.path.segments
        if len(segments) == 1 and name in getattr(entity, "parameters", {}):
            return si(entity.parameters[name])
    raise KeyError(f"the system has no parameter named {name!r}")


def _analysis(analysis: Analysis) -> str:
    return f"{analysis.kind.replace('_', ' ')}, `{analysis.directive()}`"


def _g(number: float) -> str:
    """A number as SPICE reads it, short and exact enough."""
    return f"{number:.6g}"


_PREFIXES = ((1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""),
             (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f"))


def _eng(number: float, unit: str) -> str:
    """A number to four significant figures, with an engineering prefix.

    A ratio has no unit to put a prefix on, so it is written plainly.
    """
    if not unit:
        return f"{number:.4g}"
    if number == 0:
        return f"0 {unit}".strip()
    magnitude = abs(number)
    for scale, prefix in _PREFIXES:
        if magnitude >= scale * 0.9995:
            return f"{number / scale:.4g} {prefix}{unit}".strip()
    return f"{number:.4g} {unit}".strip()
