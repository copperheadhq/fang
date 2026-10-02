"""Spec: Verification Questions Are Declared; The Bench Is Explicit; The Cheapest
Verification Level Is Chosen And Recorded; Verification Tools Sit Behind One
Protocol; Measurements Re-enter Through The Commit Gate; A Failing Measurement
Is Recorded And Not Applied; The Verify Command."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import FIXED_TIME

from fang import diagnostics
from fang.checks import DEFAULT_CHECKS
from fang.cli import EXIT_FAILED, EXIT_OK, main
from fang.constraints import CheckStatus, Comparison, Literal, Ref, Truth
from fang.diagnostics import REGISTRY, FangError
from fang.diff import ChangeClass
from fang.elaborate import elaborate
from fang.entities import Requirement, Verification
from fang.graph import KernelGraph, Policy, SetParameter, Transaction
from fang.identity import Identity, authored, derive
from fang.interfaces import AnalogIn, AnalogOut, Pin, PinMap
from fang.lang import (
    Electrical,
    Parameter,
    Part,
    System,
    V,
    kHz,
    kOhm,
    mA,
    ms,
    mV,
    nF,
    require,
    uV,
)
from fang.parts import Capacitor, Resistor
from fang.provenance import (
    Actor,
    ActorKind,
    Confidence,
    Provenance,
    ProvenanceOrigin,
    ProvenanceRecord,
)
from fang.rationale import Requires, Verifies
from fang.serialization import (
    canonical_bytes,
    canonical_dumps,
    canonical_record_stream,
    read_record_stream,
)
from fang.simulation import (
    ACSweep,
    BackendUnavailable,
    BenchItem,
    DeckMeasure,
    Level,
    NgspiceBackend,
    NgspiceDialect,
    OperatingPoint,
    RawResult,
    SimulationError,
    Subcircuit,
    Transient,
    bench_device,
    read_subcircuit,
)
from fang.traits import Simulatable
from fang.units import Quantity
from fang.values import Value, ValueStatus
from fang.workspace import Workspace
from fang.verification import (
    ANSWERED,
    DECIDED,
    EVALUATOR,
    FAILED,
    METHOD_LEVELS,
    NGSPICE,
    NOT_RUNNABLE,
    REJECTED,
    UNROUTABLE,
    UNSUPPORTED,
    Average,
    Crossing,
    Job,
    MeasuredFacts,
    Measurement,
    NotRunnable,
    Question,
    RawRun,
    Simulates,
    SpiceTool,
    Tool,
    ToolRegistry,
    answer,
    assumed_provenance,
    carry_measurements,
    constraint_statuses,
    constraints_over,
    default_tools,
    questions,
    reelaboration,
    reenter,
    register_method,
    register_tool,
    route,
    verify,
)


# ==========================================================================
# Diagnostics and entity fields
# ==========================================================================

SIM_CODES = (
    "SIM_UNDECLARED_PARAMETER",
    "SIM_QUESTION_RESULT",
    "SIM_UNRESOLVED_SURFACE",
    "SIM_MISSING_BENCH",
    "SIM_LOAD_DIMENSION",
    "SIM_MODEL_PORT_UNREACHED",
    "SIM_OUTSIDE_MODEL_RANGE",
    "SIM_EXCLUSION_WITHOUT_REASON",
)


def test_the_sim_codes_are_allocated_in_their_own_area_and_none_is_reused():
    codes = [getattr(diagnostics, name) for name in SIM_CODES]
    assert codes == [f"SIM-{n:04d}" for n in range(1, len(codes) + 1)]
    descriptions = [REGISTRY.get(code).description for code in codes]
    assert len(set(descriptions)) == len(descriptions)
    for code in codes:
        assert REGISTRY.get(code).area == "SIM"


def test_a_sim_code_is_never_reallocated_to_another_condition():
    with pytest.raises(ValueError, match="never reused"):
        REGISTRY.allocate(diagnostics.SIM_MISSING_BENCH, "something else entirely")


def test_a_verification_nobody_ran_serializes_as_it_always_did():
    plain = Verification(authored("VER-1"), verifies="REQ-1", method="inspection")
    assert "level" not in plain.as_dict() and "tool" not in plain.as_dict()


def test_a_verification_a_tool_answered_names_the_level_and_the_tool():
    answered = Verification(
        authored("VER-1"), verifies="REQ-1", method="simulation",
        result="PASS", level="circuit", tool="ngspice",
    )
    assert answered.as_dict()["level"] == "circuit"
    assert answered.as_dict()["tool"] == "ngspice"


def test_an_unbounded_range_serializes_canonically_and_compares_as_an_interval():
    """An event observed not to occur before a run's end is the range from that
    end to infinity; interval comparison decides exactly what was observed."""
    after_the_run = Quantity.range("2", "Infinity", "s")
    assert canonical_dumps(after_the_run.as_dict()) == (
        '{"kind":"range","max":"Infinity","min":"2","unit":"s"}'
    )
    assert Quantity.range("2", Decimal("Infinity"), "s").as_dict()["max"] == "Infinity"

    def resolve(entity, attr):
        return Value.inferred(after_the_run, "EVD-1", "1")

    first_read = Ref("CMP-1", "first_read", after_the_run.dimension)
    within = Comparison("le", (first_read, Literal.of(Quantity.scalar("200", "ms"))))
    beyond = Comparison("ge", (first_read, Literal.of(Quantity.scalar("1", "s"))))
    assert within.evaluate(resolve) is Truth.FALSE
    assert beyond.evaluate(resolve) is Truth.TRUE


def test_a_nan_has_no_canonical_form():
    with pytest.raises(ValueError, match="NaN"):
        Quantity.scalar(Decimal("NaN"), "V").as_dict()


# ==========================================================================
# Declaring questions
# ==========================================================================

PROJECT = "PRJ-VERIFY"


class Jack(Part):
    """A two-wire signal connection: a tip, and a sleeve that is ground."""

    designator_prefix = "J"
    line = AnalogOut()
    TIP = Pin("TIP", role="analog", number="1")
    SLEEVE = Pin("SLEEVE", role="ground", number="2")
    pinmap = PinMap({"line.signal": "TIP", "line.ref": "SLEEVE"})


def corner_question(**overrides):
    arguments = dict(
        measures={"corner": Crossing("outlet.line", level=707.1 * mV, edge="falling")},
        supplies={"inlet.line": 1 * V},
        analysis=ACSweep(variation="dec", points=100, start="10", stop="1meg"),
        abstracted=("inlet", "outlet"),
    )
    arguments.update(overrides)
    return Simulates("corner_spec", **arguments)


class Filter(System):
    """A first-order RC low-pass between two jacks."""

    corner_spec = Requires("The corner lies between 1.5 kHz and 1.7 kHz")
    corner = Parameter("Hz", description="the -3 dB corner, as measured")

    inlet = Jack()
    outlet = Jack()
    r = Resistor(resistance=10 * kOhm)
    c = Capacitor(capacitance=10 * nF)

    by_simulation = corner_question()

    def architecture(self):
        self.inlet.line.signal >> self.r.p1
        self.r.p2 >> self.c.p1
        self.c.p2 >> self.inlet.line.ref
        self.outlet.line.signal >> self.c.p1
        self.outlet.line.ref >> self.c.p2

    def constraints(self):
        require(self.corner >= 1.5 * kHz)
        require(self.corner <= 1.7 * kHz)


def build(system=Filter):
    result = elaborate(system, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


def verification_of(snapshot, attribute="by_simulation") -> Verification:
    return next(
        e for e in snapshot.entities.values()
        if isinstance(e, Verification) and e.identity.display_name == attribute
    )


def test_a_question_cannot_state_its_own_answer():
    with pytest.raises(FangError) as raised:
        corner_question(result="PASS")
    assert raised.value.diagnostic.code == diagnostics.SIM_QUESTION_RESULT
    # Not even an explicit "nothing": a result is produced by a run.
    with pytest.raises(FangError):
        corner_question(result=None)


def test_a_declared_question_becomes_an_unanswered_verification():
    snapshot = build().snapshot
    verification = verification_of(snapshot)
    requirement = next(e for e in snapshot.entities.values() if isinstance(e, Requirement))
    question = verification.extensions["question"]

    assert verification.result == "UNKNOWN"
    assert verification.verifies == requirement.id
    assert verification.method == "simulation"
    assert verification.source_location is not None
    system = derive(PROJECT, "block", "system").id
    assert [m["parameter"] for m in question["measures"]] == [f"{system}.corner"]
    assert question["bench"]["supplies"] == [
        {"surface": "inlet.line", "quantity": {"kind": "scalar", "unit": "V", "value": "1"}}
    ]
    assert question["bench"]["analysis"]["kind"] == "ac"


def test_every_surface_is_resolved_to_pins_at_elaboration():
    snapshot = build().snapshot
    question = verification_of(snapshot).extensions["question"]
    outlet = derive(PROJECT, "component", "system.outlet").id
    assert question["surfaces"]["outlet.line"] == {
        "signal": {"component": outlet, "pin": "TIP"},
        "return": {"component": outlet, "pin": "SLEEVE"},
    }
    assert {part["name"] for part in question["abstracted"]} == {"inlet", "outlet"}


def test_two_elaborations_of_a_question_are_byte_identical():
    first, second = build().snapshot, build().snapshot
    assert canonical_bytes(first.as_dict()) == canonical_bytes(second.as_dict())


def test_a_measure_naming_an_undeclared_parameter_fails_elaboration():
    class Misnamed(Filter):
        by_simulation = corner_question(
            measures={"knee": Crossing("outlet.line", level=707.1 * mV)}
        )

    result = elaborate(Misnamed, project_id=PROJECT)
    assert not result.ok
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == diagnostics.SIM_UNDECLARED_PARAMETER
    assert "'knee'" in diagnostic.message
    assert diagnostic.location is not None


def test_a_surface_with_no_pins_fails_elaboration_naming_it():
    class Probed(Filter):
        board_in = Electrical()
        by_simulation = corner_question(supplies={"board_in": 1 * V})

    result = elaborate(Probed, project_id=PROJECT)
    assert not result.ok
    assert result.diagnostics[0].code == diagnostics.SIM_UNRESOLVED_SURFACE
    assert "'board_in'" in result.diagnostics[0].message
    assert "system's own surface is not a probe" in result.diagnostics[0].message

    class Mistyped(Filter):
        by_simulation = corner_question(supplies={"inlet.jack": 1 * V})

    result = elaborate(Mistyped, project_id=PROJECT)
    assert result.diagnostics[0].code == diagnostics.SIM_UNRESOLVED_SURFACE
    assert "'inlet.jack'" in result.diagnostics[0].message


def test_a_load_is_a_current_or_a_resistance_and_nothing_else():
    corner_question(loads={"outlet.line": 1 * mA})
    corner_question(loads={"outlet.line": 10 * kOhm})
    with pytest.raises(FangError) as raised:
        corner_question(loads={"outlet.line": 3 * V})
    assert raised.value.diagnostic.code == diagnostics.SIM_LOAD_DIMENSION
    assert "outlet.line" in raised.value.diagnostic.message


def test_a_window_in_the_wrong_dimension_is_refused_where_it_is_written():
    with pytest.raises(FangError) as raised:
        corner_question(measures={"corner": Average("outlet.line", after=1 * ms)})
    assert raised.value.diagnostic.code == diagnostics.UNIT_DIMENSION_MISMATCH


def test_a_measure_producing_the_wrong_dimension_fails_elaboration():
    class Averaged(Filter):
        by_simulation = corner_question(measures={"corner": Average("outlet.line")})

    result = elaborate(Averaged, project_id=PROJECT)
    assert result.diagnostics[0].code == diagnostics.UNIT_DIMENSION_MISMATCH


def test_a_question_reads_back_from_its_record_without_the_program():
    """A question in the graph is data: its measures rebuild from the record,
    and the values and provenance beside it round-trip exactly."""
    from fang.provenance import Provenance
    from fang.verification import Measure

    snapshot = build().snapshot
    verification = verification_of(snapshot)
    record = json.loads(canonical_dumps(verification.as_dict()))

    for entry in record["extensions"]["question"]["measures"]:
        assert Measure.from_dict(entry["measure"]).as_dict() == entry["measure"]
    assert Identity.from_dict(record["identity"]) == verification.identity
    assert Provenance.from_list(record["provenance"]).as_list() == verification.provenance.as_list()

    value = Value.inferred(Quantity.range("2", "Infinity", "s"), "EVD-1", "0.5")
    assert Value.from_dict(json.loads(canonical_dumps(value.as_dict()))) == value


def test_a_verification_by_inspection_elaborates_exactly_as_before(tmp_path):
    class Inspected(Filter):
        looked_at = Verifies("corner_spec", method="inspection", result="PASS")

    result = build(Inspected)
    inspected = verification_of(result.snapshot, "looked_at")
    assert inspected.result == "PASS"
    assert inspected.method == "inspection"
    assert inspected.extensions == {}
    assert "extensions" not in inspected.as_dict()

    # It is not a question, so nothing routes it, and a verify leaves it be.
    assert Question.of(inspected) is None
    assert inspected.id not in {q.id for q in questions(result.snapshot)}
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    tool, tools = canned()
    outcomes = verify(graph, traits=result.traits, tools=tools, workspace=tmp_path)
    assert [o.question.id for o in outcomes] == [verification_of(result.snapshot).id]
    assert graph.head.entities[inspected.id].as_dict() == inspected.as_dict()


# ==========================================================================
# The protocol, routing and the runner
# ==========================================================================

#: What ngspice 45.2 printed for the filter's corner question, captured from
#: the installed binary: one measure reported, one reported as failed.
FLOORED_OUTPUT = """
Note: No compatibility mode selected!


Circuit: * fang question system.by_simulation

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

Using SPARSE 1.3 as Direct Linear Solver

No. of Data Rows : 501
fang_m0             =  1.591612e+03
 meas ac fang_m1 when fang_s1=0.000001 fall=1 failed!

Note: Simulation executed from .control section
"""

#: The same run with the failing measure taken out.
FILTER_OUTPUT = FLOORED_OUTPUT.replace(
    " meas ac fang_m1 when fang_s1=0.000001 fall=1 failed!\n", ""
)

#: What ngspice 45.2 printed for the buck regulator's transient question.
BUCK_OUTPUT = """
No. of Data Rows : 159028
fang_m0             =  3.285035e+00 from=  1.000000e-03 to=  1.200000e-03
fang_m1             =  1.898368e-03 from=  1.000000e-03 to=  1.200000e-03
Note: Simulation executed from .control section
"""


@dataclass
class CannedBackend:
    """A SPICE backend that answers with output captured from ngspice 45.2,
    so the protocol and re-entry are tested with no binary installed."""

    stdout: str = FILTER_OUTPUT
    installed: bool = True
    exit_status: int = 0
    runs: list = field(default_factory=list)

    def available(self) -> bool:
        return self.installed

    def version(self) -> str:
        if not self.installed:
            raise BackendUnavailable("ngspice is not installed")
        return "ngspice-45.2"

    def run(self, netlist, *, workspace, timeout=60):
        self.runs.append(netlist)
        return RawResult("ngspice", "ngspice-45.2", self.stdout, self.exit_status, netlist)


def canned(stdout: str = FILTER_OUTPUT, **kwargs):
    tool = SpiceTool("ngspice", NgspiceDialect(), CannedBackend(stdout, **kwargs))
    return tool, ToolRegistry((tool,))


@dataclass
class Spy:
    """A tool that records whether it was asked to prepare anything."""

    name: str
    level: Level = Level.CIRCUIT
    methods: tuple = ("simulation",)
    installed: bool = True
    prepared: list = field(default_factory=list)

    def covers(self, question) -> bool:
        return question.method in self.methods

    def available(self) -> bool:
        return self.installed

    def version(self) -> str:
        return "spy-1"

    def prepare(self, snapshot, question, *, traits=None) -> Job:
        self.prepared.append(question.id)
        return Job.single(self.name, question, snapshot.hash, "input.txt", "spy")

    def run(self, job, *, workspace) -> RawRun:
        return RawRun(self.name, "spy-1", 0)

    def read(self, job, raw):
        return tuple(
            Measurement(
                entry.name, entry.parameter, None, self.name, raw.version, job.hash,
                Decimal(1), reason="a spy measures nothing",
            )
            for entry in job.question.measures
        )


SYSTEM = derive(PROJECT, "block", "system").id


def graph_of(system=Filter, **kwargs):
    result = build(system)
    return result, KernelGraph(result.snapshot, checks=DEFAULT_CHECKS, **kwargs)


def answered(tmp_path, system=Filter, stdout=FILTER_OUTPUT, **kwargs):
    result, graph = graph_of(system, **kwargs)
    tool, tools = canned(stdout)
    question = questions(graph.head)[0]
    outcome = answer(
        graph, question, traits=result.traits, tools=tools, workspace=tmp_path,
        record_time=FIXED_TIME,
    )
    return graph, outcome


def test_the_default_registry_holds_its_tools_in_routing_order():
    assert default_tools().names() == ["ngspice"]
    assert isinstance(NGSPICE, Tool)
    assert isinstance(Spy("spy"), Tool)


def test_a_tool_registers_after_the_built_ins_or_before_a_tool_it_names():
    registry = default_tools()
    register_tool(Spy("late"), registry=registry)
    register_tool(Spy("early"), before="ngspice", registry=registry)
    assert registry.names() == ["early", "ngspice", "late"]
    register_tool(Spy("late", level=Level.EXTERNAL), registry=registry)
    assert registry.names() == ["early", "ngspice", "late"]
    assert registry.get("late").level is Level.EXTERNAL


def test_preparation_is_deterministic():
    """The same question over the same snapshot is a byte-identical job,
    and so is the same question over a second elaboration of the program."""
    result = build()
    question = questions(result.snapshot)[0]
    first = NGSPICE.prepare(result.snapshot, question, traits=result.traits)
    second = NGSPICE.prepare(result.snapshot, question, traits=result.traits)
    assert first.input == second.input
    assert first.hash == second.hash

    again = build()
    third = NGSPICE.prepare(again.snapshot, questions(again.snapshot)[0], traits=again.traits)
    assert third.input == first.input and third.hash == first.hash


def test_a_job_is_a_bundle_and_its_hash_covers_all_of_it():
    question = questions(build().snapshot)[0]
    bundle = Job("renode", question, "sha256:x", {"run.resc": "quit", "fw.elf": b"\x7fELF"})
    with pytest.raises(ValueError, match="bundle"):
        bundle.input
    moved = Job("renode", question, "sha256:y", dict(bundle.files), sources={"fw.elf": "/a"})
    assert moved.hash == bundle.hash
    for changed in (
        Job("renode", question, "sha256:x", {"run.resc": "quit", "fw.elf": b"\x7fELG"}),
        Job("renode", question, "sha256:x", dict(bundle.files), extra={"seed": "7"}),
        Job("renode", question, "sha256:x", dict(bundle.files), inputs={"fw.elf": "sha256:1"}),
    ):
        assert changed.hash != bundle.hash


def test_an_undecided_circuit_question_routes_to_a_circuit_simulator():
    snapshot = build().snapshot
    routed = route(snapshot, questions(snapshot)[0])
    assert routed.level is Level.CIRCUIT
    assert routed.tool == "ngspice"
    assert not routed.decided


def test_a_question_the_evaluator_decides_runs_no_tool(tmp_path):
    """The corner reached the graph by another path -- a hand calculation an
    engineer entered -- so the evaluator already decides the constraint."""
    result, graph = graph_of()
    graph.apply(
        Transaction(
            graph.head.hash,
            (
                SetParameter(
                    target=SYSTEM, name="corner",
                    value=Value.inferred(Quantity.scalar("1600", "Hz"), "SRC-HAND-CALC", "1"),
                ),
            ),
        )
    )
    spy = Spy("spy")
    question = questions(graph.head)[0]
    routed = route(graph.head, question, tools=ToolRegistry((spy,)))
    assert routed.decided and routed.level is Level.EQUATION and routed.tool == EVALUATOR

    outcome = answer(graph, question, tools=ToolRegistry((spy,)), workspace=tmp_path)
    assert spy.prepared == []
    assert outcome.status == DECIDED and outcome.result == "PASS"
    verification = graph.head.entities[question.id]
    assert (verification.result, verification.level, verification.tool) == (
        "PASS", "equation", EVALUATOR,
    )


def test_a_question_nothing_covers_is_unroutable_and_not_answered_elsewhere(tmp_path):
    result, graph = graph_of()
    question = questions(graph.head)[0]
    # A tool at another level that would happily answer is not asked.
    eager = Spy("eager", level=Level.EQUATION)
    tools = ToolRegistry((eager,))
    routed = route(graph.head, question, tools=tools)
    assert not routed.routed
    assert "circuit level" in routed.reason

    outcome = answer(graph, question, tools=tools, workspace=tmp_path)
    assert outcome.status == UNROUTABLE and outcome.result == "UNKNOWN"
    assert eager.prepared == []


def test_a_question_naming_a_tool_routes_only_to_that_tool():
    class Named(Filter):
        by_simulation = corner_question(tool="xyce")

    snapshot = build(Named).snapshot
    routed = route(snapshot, questions(snapshot)[0])
    assert not routed.routed and "xyce" in routed.reason


def test_method_routing_is_extended_by_registering_a_method(monkeypatch):
    from dataclasses import replace

    snapshot = build().snapshot
    question = replace(questions(snapshot)[0], method="emulation")
    # fang.emulation registers this method when it is imported; take it out for
    # the length of the test, so the answer does not depend on test order.
    monkeypatch.delitem(METHOD_LEVELS, "emulation", raising=False)
    assert "no verification level" in route(snapshot, question).reason

    monkeypatch.setitem(METHOD_LEVELS, "emulation", Level.BEHAVIOURAL)
    renode = Spy("renode", level=Level.BEHAVIOURAL, methods=("emulation",))
    routed = route(snapshot, question, tools=ToolRegistry((NGSPICE, renode)))
    assert (routed.level, routed.tool) == (Level.BEHAVIOURAL, "renode")
    with pytest.raises(ValueError, match="already routes"):
        register_method("simulation", Level.EXTERNAL)


def test_a_question_without_a_supply_does_not_run(tmp_path):
    class Unpowered(Filter):
        by_simulation = corner_question(supplies={})

    result, graph = graph_of(Unpowered)
    question = questions(graph.head)[0]
    with pytest.raises(NotRunnable) as raised:
        NGSPICE.prepare(graph.head, question, traits=result.traits)
    assert raised.value.code == diagnostics.SIM_MISSING_BENCH
    assert "names no supply" in str(raised.value)

    tool, tools = canned()
    outcome = answer(graph, question, traits=result.traits, tools=tools, workspace=tmp_path)
    assert outcome.status == NOT_RUNNABLE and "names no supply" in outcome.message
    assert tool.backend.runs == []


def test_a_missing_tool_reports_unsupported_by_name_and_nothing_stands_in(tmp_path):
    result, graph = graph_of()
    absent = SpiceTool("ngspice", NgspiceDialect(), NgspiceBackend(executable="not-a-simulator"))
    stand_in = Spy("stand_in")
    before = graph.head.hash
    outcome = answer(
        graph, questions(graph.head)[0], traits=result.traits,
        tools=ToolRegistry((absent, stand_in)), workspace=tmp_path,
    )
    assert outcome.status == UNSUPPORTED
    assert "ngspice is not installed" in outcome.message
    assert outcome.result == "UNKNOWN"
    assert stand_in.prepared == []
    assert graph.head.hash == before


def test_preparation_refuses_a_surface_that_resolves_to_no_pins():
    """Elaboration refuses such a surface first; a question built any other
    way meets the same refusal when it is prepared."""
    from dataclasses import replace

    result = build()
    question = questions(result.snapshot)[0]
    surfaces = dict(question.data["surfaces"])
    del surfaces["outlet.line"]
    broken = replace(question, data={**question.data, "surfaces": surfaces})
    with pytest.raises(NotRunnable) as raised:
        NGSPICE.prepare(result.snapshot, broken, traits=result.traits)
    assert raised.value.code == diagnostics.SIM_UNRESOLVED_SURFACE
    assert "'outlet.line'" in str(raised.value)


def test_bench_items_are_assumptions_and_abstracted_parts_are_coverage_gaps():
    class Loaded(Filter):
        by_simulation = corner_question(loads={"outlet.line": 10 * kOhm})

    result = build(Loaded)
    job = NGSPICE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits)
    assert "a 1 V supply at inlet.line" in job.assumptions
    assert "a 10 kOhm load across outlet.line" in job.assumptions
    assert "system.inlet is abstracted, not modelled" in job.coverage_gaps
    assert "system.outlet is abstracted, not modelled" in job.coverage_gaps


# -- a modelled part ----------------------------------------------------------

FOLLOWER = """* A unity-gain buffer: what it does, and nothing about how.
.subckt follower in out
+ gnd params: gain=1
Ebuf out gnd in gnd 1
Rin in gnd 1e9
.ends follower
"""


class Follower(Part):
    """A buffer whose behaviour comes from a subcircuit model."""

    designator_prefix = "U"
    signal_in = AnalogIn()
    signal_out = AnalogOut()
    IN = Pin("IN", role="analog", number="1")
    OUT = Pin("OUT", role="analog", number="2")
    GND = Pin("GND", role="ground", number="3")
    pinmap = PinMap(
        {
            "signal_in.signal": "IN", "signal_in.ref": "GND",
            "signal_out.signal": "OUT", "signal_out.ref": "GND",
        }
    )


def buffered(model: Path, *, provenance=None, pin_map=None):
    """The filter with a modelled buffer in front of it."""

    class Buffered(Filter):
        buffer = Follower()
        by_simulation = corner_question()

        def __init__(self, **overrides):
            super().__init__(**overrides)
            self.buffer.add_trait(
                Simulatable(
                    backends=("ngspice",),
                    source=str(model),
                    pin_map=pin_map or {"IN": "in", "OUT": "out", "GND": "gnd"},
                    provenance=provenance if provenance is not None else Provenance(),
                    not_modelled=("slew rate and output current limit",),
                )
            )

        def architecture(self):
            self.inlet.line.signal >> self.buffer.signal_in.signal
            self.inlet.line.ref >> self.buffer.signal_in.ref
            self.buffer.signal_out.signal >> self.r.p1
            self.r.p2 >> self.c.p1
            self.c.p2 >> self.buffer.signal_out.ref
            self.outlet.line.signal >> self.c.p1
            self.outlet.line.ref >> self.c.p2

    return Buffered


@pytest.fixture
def follower(tmp_path) -> Path:
    path = tmp_path / "follower.sub"
    path.write_text(FOLLOWER)
    return path


def test_a_modelled_part_is_instantiated_from_its_model(follower):
    result = build(buffered(follower))
    job = NGSPICE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits)
    deck = job.input
    instance = next(line for line in deck.splitlines() if line.startswith("XU"))
    # In the model's port order -- in, out, gnd -- with gnd on the ground node.
    _, node_in, node_out, node_gnd, name = instance.split()
    assert name == "follower" and node_gnd == "0" and node_in != node_out
    # Referenced, never inlined, and the file's digest kept for the evidence.
    assert ".include models/follower.sub" in deck
    assert "Ebuf" not in deck
    digest = "sha256:" + hashlib.sha256(FOLLOWER.encode()).hexdigest()
    assert job.inputs == {"models/follower.sub": digest}
    assert "system.buffer's model: slew rate and output current limit" in job.coverage_gaps


def test_a_model_port_no_pin_reaches_is_refused_by_name(tmp_path):
    model = tmp_path / "follower.sub"
    model.write_text(FOLLOWER.replace("+ gnd params", "+ gnd vcc params"))
    result = build(buffered(model))
    with pytest.raises(NotRunnable) as raised:
        NGSPICE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits)
    assert raised.value.code == diagnostics.SIM_MODEL_PORT_UNREACHED
    assert "vcc" in str(raised.value)


def test_a_subcircuit_line_is_read_in_its_declared_order():
    assert read_subcircuit(FOLLOWER) == Subcircuit("follower", ("in", "out", "gnd"))
    with pytest.raises(SimulationError, match="no .subckt"):
        read_subcircuit("* nothing here\nR1 1 0 1k\n")


def test_confidence_is_bounded_by_model_provenance(follower):
    over_primitives = build()
    assumed = build(buffered(follower, provenance=assumed_provenance("a stand-in")))
    cited = build(
        buffered(
            follower,
            provenance=Provenance().append(
                ProvenanceRecord(
                    ProvenanceOrigin.IMPORTED, "vendor_model", Actor(ActorKind.ADAPTER, "vendor"),
                    "REV-000000", FIXED_TIME, confidence=Confidence.ASSERTED,
                )
            ),
        )
    )

    def confidence(result):
        return NGSPICE.prepare(
            result.snapshot, questions(result.snapshot)[0], traits=result.traits
        ).confidence

    assert confidence(over_primitives) == Decimal(1)
    assert confidence(cited) == Decimal(1)
    assert confidence(assumed) < confidence(over_primitives)


# -- lowering ------------------------------------------------------------------


def test_bench_items_lower_to_v_i_and_r_devices_by_dimension():
    supply = BenchItem("supply", "controller.vin", Quantity.scalar("12", "V"), "3", "0")
    assert bench_device(supply, 0) == "Vfang_supply0 3 0 DC 12"
    assert bench_device(supply, 0, ac=True) == "Vfang_supply0 3 0 DC 12 AC 12"
    drawn = BenchItem("load", "rail_out.dc", Quantity.scalar("1.5", "A"), "5", "0")
    assert bench_device(drawn, 0) == "Ifang_load0 5 0 DC 1.5"
    across = BenchItem("load", "rail_out.dc", Quantity.scalar("2.2", "Ohm"), "5", "0")
    assert bench_device(across, 1) == "Rfang_load1 5 0 2.2"
    wrong = BenchItem("load", "rail_out.dc", Quantity.scalar("3", "V"), "5", "0")
    with pytest.raises(SimulationError) as raised:
        bench_device(wrong, 0)
    assert raised.value.code == diagnostics.SIM_LOAD_DIMENSION


def test_a_question_deck_carries_its_bench_and_measures_through_a_control_block():
    class Loaded(Filter):
        by_simulation = corner_question(loads={"outlet.line": 10 * kOhm})

    result = build(Loaded)
    deck = NGSPICE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits).input
    lines = deck.splitlines()
    assert any(line.startswith("Vfang_supply0 ") and line.endswith(" 0 DC 1 AC 1") for line in lines)
    assert any(line.startswith("Rfang_load0 ") and line.endswith(" 0 10000") for line in lines)
    control = lines[lines.index(".control"): lines.index(".endc") + 1]
    assert control[1] == "ac dec 100 10 1meg"
    assert control[3] == "meas ac fang_m0 WHEN fang_s0=0.7071 FALL=1"
    assert lines[-1] == ".end"


def test_a_peak_to_peak_lowers_to_a_measurement_between_node_and_return():
    measure = DeckMeasure(
        "fang_m0", "peak_to_peak", "5", "4", after=Decimal("0.001"), until=Decimal("0.0012")
    )
    lines = NgspiceDialect().control(Transient(stop="1.2ms", step="10ns"), [measure])
    assert lines == [
        ".control",
        "tran 10ns 1.2ms",
        "let fang_s0 = v(5)-v(4)",
        "meas tran fang_m0 PP fang_s0 from=0.001 to=0.0012",
        ".endc",
    ]
    held = DeckMeasure("fang_m0", "value_at", "5")
    assert NgspiceDialect().control(OperatingPoint(), [held])[2:4] == [
        "let fang_m0 = v(5)", "print fang_m0",
    ]


def test_ngspice_output_is_read_into_decimals_and_nothing_else():
    slots = [DeckMeasure("fang_m0", "crossing", ""), DeckMeasure("fang_m1", "crossing", "")]
    found = NgspiceDialect().parse(FLOORED_OUTPUT, slots)
    assert found["fang_m0"] == Decimal("1591.612")
    assert "failed" in found["fang_m1"]

    buck = NgspiceDialect().parse(BUCK_OUTPUT, slots)
    assert buck == {"fang_m0": Decimal("3.285035"), "fang_m1": Decimal("0.001898368")}
    absent = NgspiceDialect().parse("No. of Data Rows : 1\n", slots)
    assert absent["fang_m0"] == "ngspice's output does not report it"


class Floored(Filter):
    floor = Parameter("Hz", description="where the output falls below 1 uV, which it never does")
    by_simulation = corner_question(
        measures={
            "corner": Crossing("outlet.line", level=707.1 * mV, edge="falling"),
            "floor": Crossing("outlet.line", level=1 * uV, edge="falling"),
        }
    )


def test_a_measurement_carries_a_decimal_in_its_parameters_unit_with_its_tool(tmp_path):
    result = build(Floored)
    tool, _ = canned(FLOORED_OUTPUT)
    question = questions(result.snapshot)[0]
    job = tool.prepare(result.snapshot, question, traits=result.traits)
    corner, floor = tool.read(job, tool.run(job, workspace=tmp_path))

    assert corner.quantity == Quantity.scalar("1591.612", "Hz")
    assert (corner.tool, corner.version, corner.job) == ("ngspice", "ngspice-45.2", job.hash)
    # A measure reported as failed is not invented.
    assert floor.quantity is None and "failed" in floor.reason


def test_a_measure_the_output_does_not_report_leaves_the_result_unknown(tmp_path):
    graph, outcome = answered(tmp_path, Floored, FLOORED_OUTPUT)
    assert outcome.status == ANSWERED
    assert outcome.result == "UNKNOWN"
    assert "floor" in outcome.message
    head = graph.head
    assert head.entities[SYSTEM].parameters["floor"].known is False
    measures = head.entities[outcome.evidence].extensions["measurement"]["measures"]
    assert {"name": "floor", "parameter": f"{SYSTEM}.floor",
            "reason": "ngspice reported the measure as failed"} in measures


@pytest.mark.skipif(not NGSPICE.available(), reason="ngspice is not installed here")
def test_the_installed_ngspice_measures_the_corner_and_fails_the_floor(tmp_path):
    result = build(Floored)
    question = questions(result.snapshot)[0]
    job = NGSPICE.prepare(result.snapshot, question, traits=result.traits)
    raw = NGSPICE.run(job, workspace=tmp_path)
    corner, floor = NGSPICE.read(job, raw)
    assert raw.version.startswith("ngspice")
    assert Decimal("1580") < corner.quantity.value < Decimal("1600")
    assert floor.quantity is None


# ==========================================================================
# Re-entry through the gate
# ==========================================================================


def test_a_measured_parameter_is_an_inferred_value_sourced_from_its_evidence(tmp_path):
    graph, outcome = answered(tmp_path)
    assert outcome.status == ANSWERED and outcome.result == "PASS"
    value = graph.head.entities[SYSTEM].parameters["corner"]
    assert value.status is ValueStatus.INFERRED and not value.is_explicit
    assert value.source == outcome.evidence
    assert value.confidence == Decimal(1)
    assert value.quantity == Quantity.scalar("1591.612", "Hz")

    operations = [op.op for op in outcome.proposal.transaction.operations]
    assert operations == ["set_parameter", "add_entity", "remove_entity", "add_entity"]


def test_the_evidence_carries_the_whole_measurement_record(tmp_path, follower):
    graph, outcome = answered(tmp_path, buffered(follower))
    record = graph.head.entities[outcome.evidence].extensions["measurement"]
    assert record["tool"] == {"name": "ngspice", "version": "ngspice-45.2"}
    assert record["level"] == "circuit"
    assert record["job"] == outcome.job.hash
    assert record["measures"] == [
        {"name": "corner", "parameter": f"{SYSTEM}.corner", "unit": "Hz", "value": "1591.612"}
    ]
    assert "a 1 V supply at inlet.line" in record["assumptions"]
    assert "system.inlet is abstracted, not modelled" in record["coverage_gaps"]
    digest = "sha256:" + hashlib.sha256(FOLLOWER.encode()).hexdigest()
    assert record["inputs"] == [{"path": "models/follower.sub", "hash": digest}]


def test_the_verification_keeps_its_identity_and_names_its_answer(tmp_path):
    result, before = graph_of()
    declared = verification_of(before.head)
    graph, outcome = answered(tmp_path)
    verification = graph.head.entities[declared.id]
    assert verification.identity == declared.identity
    assert (verification.result, verification.level, verification.tool) == (
        "PASS", "circuit", "ngspice",
    )
    assert verification.evidence == (outcome.evidence,)
    run = verification.provenance.records[-1]
    assert run.activity == "verification_run"
    assert (run.actor.id, run.actor.version) == ("ngspice", "ngspice-45.2")
    assert len(verification.provenance) == len(declared.provenance) + 1


def test_the_undecided_constraint_is_decided_by_the_gate(tmp_path):
    result, graph = graph_of()
    question = questions(graph.head)[0]
    over = {c.id for c in constraints_over(graph.head, question.parameters)}
    assert len(over) == 2
    assert set(constraint_statuses(graph.head, question).values()) == {CheckStatus.UNKNOWN}

    graph, outcome = answered(tmp_path)
    decided = {c.subject: c.status for c in outcome.proposal.checks if c.subject in over}
    assert decided == {subject: CheckStatus.PASS for subject in over}


class Tightened(Filter):
    """The same filter held to a corner the circuit cannot meet."""

    def constraints(self):
        require(self.corner >= 1 * kHz)
        require(self.corner <= 1.2 * kHz)


def test_a_value_that_breaks_a_hard_constraint_never_reaches_the_head(tmp_path):
    graph, outcome = answered(tmp_path, Tightened)
    assert outcome.status == FAILED and outcome.result == "FAIL"
    # The rejection names the constraint that failed.
    assert outcome.proposal.rejected
    failing = [d for d in outcome.proposal.diagnostics if d.code == diagnostics.TXN_GATE_BLOCKED]
    assert failing and all(d.entities[0].startswith("RULE-") for d in failing)
    # The parameter is still unknown on the head.
    assert not graph.head.entities[SYSTEM].parameters["corner"].known


def test_the_failure_is_recorded_as_knowledge(tmp_path):
    graph, outcome = answered(tmp_path, Tightened)
    verification = graph.head.entities[outcome.question.id]
    assert verification.result == "FAIL"
    assert verification.evidence == (outcome.evidence,)
    evidence = graph.head.entities[outcome.evidence]
    assert evidence.extensions["measurement"]["measures"][0]["value"] == "1591.612"
    # The second transaction set no parameter.
    assert "set_parameter" not in [op.op for op in outcome.recorded.transaction.operations]
    assert len(graph.history) == 2


def test_an_unrelated_rejection_records_nothing(tmp_path):
    graph, outcome = answered(
        tmp_path, policy=Policy(approvals_required=frozenset({"lead engineer"}))
    )
    assert outcome.status == REJECTED
    assert len(graph.history) == 1
    assert not any(e.kind == "evidence" and "measurement" in e.extensions
                   for e in graph.head.entities.values())


def test_measurements_against_a_stale_head_are_refused(tmp_path):
    result, graph = graph_of()
    tool, _ = canned()
    question = questions(graph.head)[0]
    job = tool.prepare(graph.head, question, traits=result.traits)
    raw = tool.run(job, workspace=tmp_path)
    measurements = tool.read(job, raw)

    graph.apply(
        Transaction(
            graph.head.hash,
            (SetParameter(target=SYSTEM, name="corner", value=Value.unknown(), reason="moved"),),
        )
    )
    with pytest.raises(FangError) as raised:
        reenter(graph, question, job, raw, measurements, level=Level.CIRCUIT)
    assert raised.value.diagnostic.code == diagnostics.TXN_STALE_SNAPSHOT


def test_re_elaboration_does_not_withdraw_a_measured_value(tmp_path):
    graph, outcome = answered(tmp_path)
    measured = graph.head.entities[SYSTEM].parameters["corner"]

    transaction = reelaboration(graph.head, build().snapshot)
    assert transaction.operations == ()
    proposal = graph.propose(transaction)
    assert proposal.accepted
    assert not any(c.type is ChangeClass.PARAMETER_CHANGED for c in proposal.diff)
    graph.commit(proposal)
    assert graph.head.entities[SYSTEM].parameters["corner"] == measured
    assert outcome.evidence in graph.head.entities


def test_a_workspace_round_trips_its_measurements_byte_for_byte(tmp_path):
    """What a run wrote is read back from the record stream, and an unchanged
    program rebuilt around it is the committed head."""
    graph, outcome = answered(tmp_path)
    records = read_record_stream(canonical_record_stream(graph.head.records()))
    rebuilt = carry_measurements(build().snapshot, MeasuredFacts.from_records(records))
    rebuilt = rebuilt.with_entities(rebuilt.entities, graph.head.revision_id)
    assert rebuilt.hash == graph.head.hash


def test_a_changed_question_is_answered_afresh(tmp_path):
    class Rebenched(Filter):
        by_simulation = corner_question(supplies={"inlet.line": 2 * V})

    graph, outcome = answered(tmp_path)
    rebuilt = carry_measurements(build(Rebenched).snapshot, MeasuredFacts.of(graph.head))
    assert verification_of(rebuilt).result == "UNKNOWN"
    assert not rebuilt.entities[SYSTEM].parameters["corner"].known


# ==========================================================================
# The command
# ==========================================================================

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

#: A program the command is pointed at, written to a scratch folder, with the
#: constraint and the bench as the test needs them.
PROGRAM = '''
"""An RC low-pass between two jacks."""

from fang.interfaces import AnalogOut, Pin, PinMap
from fang.lang import Parameter, Part, System, V, kHz, kOhm, mV, nF, require
from fang.parts import Capacitor, Resistor
from fang.rationale import Requires
from fang.simulation import ACSweep
from fang.verification import Crossing, Simulates


class Jack(Part):
    designator_prefix = "J"
    line = AnalogOut()
    TIP = Pin("TIP", role="analog", number="1")
    SLEEVE = Pin("SLEEVE", role="ground", number="2")
    pinmap = PinMap({"line.signal": "TIP", "line.ref": "SLEEVE"})


class Filter(System):
    corner_spec = Requires("The corner lies at or below @UPPER@ kHz")
    corner = Parameter("Hz")

    inlet = Jack()
    outlet = Jack()
    r = Resistor(resistance=10 * kOhm)
    c = Capacitor(capacitance=10 * nF)

    by_simulation = Simulates(
        "corner_spec",
        measures={"corner": Crossing("outlet.line", level=707.1 * mV, edge="falling")},
        supplies=@SUPPLIES@,
        analysis=ACSweep(variation="dec", points=100, start="10", stop="1meg"),
        abstracted=("inlet", "outlet"),
    )

    def architecture(self):
        self.inlet.line.signal >> self.r.p1
        self.r.p2 >> self.c.p1
        self.c.p2 >> self.inlet.line.ref
        self.outlet.line.signal >> self.c.p1
        self.outlet.line.ref >> self.c.p2

    def constraints(self):
        require(self.corner <= @UPPER@ * kHz)
'''


def program(tmp_path, *, upper: str = "2", supplies: str = '{"inlet.line": 1 * V}') -> str:
    path = tmp_path / "filter.py"
    path.write_text(PROGRAM.replace("@UPPER@", upper).replace("@SUPPLIES@", supplies))
    return str(path)


@pytest.fixture
def ngspice(monkeypatch):
    """ngspice as the command reaches it, answering with captured output."""
    backend = CannedBackend(FILTER_OUTPUT)
    monkeypatch.setattr(NGSPICE, "backend", backend)
    return backend


def snapshot_of(directory: Path) -> dict[str, bytes]:
    """Every file under a workspace, by path, so a change to any shows."""
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_verify_reports_each_question(tmp_path, ngspice, capsys):
    assert main(["verify", program(tmp_path), "-C", str(tmp_path)]) == EXIT_OK
    output = capsys.readouterr().out
    assert "system.by_simulation (VER-" in output
    assert "  circuit level, ngspice (ngspice-45.2)" in output
    assert "  corner = 1590 Hz" in output
    assert "  coverage gap: system.inlet is abstracted, not modelled" in output
    assert output.rstrip().endswith("PASS")


def test_a_failed_verification_exits_non_zero(tmp_path, ngspice, capsys):
    assert main(["verify", program(tmp_path, upper="1.2"), "-C", str(tmp_path)]) == EXIT_FAILED
    output = capsys.readouterr().out
    assert "failed: the gate refused the measurement" in output
    assert output.rstrip().endswith("FAIL")


def test_an_unsupported_question_is_reported_and_is_not_a_failure(tmp_path, ngspice, capsys):
    ngspice.installed = False
    assert main(["verify", program(tmp_path), "-C", str(tmp_path)]) == EXIT_OK
    output = capsys.readouterr().out
    assert "unsupported: ngspice is not installed" in output
    assert ngspice.runs == []


def test_a_question_left_unrunnable_exits_non_zero(tmp_path, ngspice, capsys):
    assert main(["verify", program(tmp_path, supplies="{}"), "-C", str(tmp_path)]) == EXIT_FAILED
    assert "not runnable: system.by_simulation names no supply" in capsys.readouterr().out


def test_a_program_with_no_questions_says_so(tmp_path, capsys):
    divider = str(EXAMPLES / "divider" / "divider.py")
    assert main(["verify", divider, "-C", str(tmp_path)]) == EXIT_OK
    assert "nothing to verify: divider.py declares no question" in capsys.readouterr().out


def test_nothing_persists_without_a_commit(tmp_path, ngspice, capsys):
    source = program(tmp_path)
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    before = snapshot_of(Workspace(tmp_path).dir)
    assert main(["verify", source, "-C", str(tmp_path)]) == EXIT_OK
    assert snapshot_of(Workspace(tmp_path).dir) == before


def test_commit_needs_an_existing_workspace(tmp_path, ngspice, capsys):
    code = main(["verify", program(tmp_path), "-C", str(tmp_path), "--commit"])
    assert code == EXIT_FAILED
    assert "run 'fang build' first" in capsys.readouterr().err
    assert not Workspace(tmp_path).exists


def test_a_commit_persists_and_a_rebuild_keeps_the_measured_value(tmp_path, ngspice, capsys):
    """Re-elaboration into the workspace does not withdraw a measured value,
    and the program is not recorded as having changed it."""
    source = program(tmp_path)
    workspace = Workspace(tmp_path)
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    built = workspace.read_manifest().snapshot

    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    committed = workspace.read_manifest().snapshot
    assert committed != built
    records = workspace.read_records()
    evidence = [r for r in records if r["kind"] == "evidence" and "measurement" in r.get("extensions", {})]
    assert len(evidence) == 1
    corner = next(r for r in records if r["kind"] == "block")["parameters"]["corner"]
    assert corner["status"] == "inferred" and corner["source"] == evidence[0]["id"]

    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    assert workspace.read_manifest().snapshot == committed
    capsys.readouterr()
    assert main(["diff", source, "-C", str(tmp_path)]) == EXIT_OK
    assert capsys.readouterr().out.strip() == "no change"

    runs = len(ngspice.runs)
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "equation level, by the constraint evaluator; nothing runs" in output
    assert "nothing new to commit" in output
    assert len(ngspice.runs) == runs
