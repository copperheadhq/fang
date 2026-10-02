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
from fang.cli import EXIT_FAILED, EXIT_OK, load_system, main
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
    us,
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
    XyceBackend,
    XyceDialect,
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
    XYCE,
    Average,
    Crossing,
    Job,
    Maximum,
    MeasuredFacts,
    Minimum,
    PeakToPeak,
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


def test_a_program_cannot_give_a_measured_parameter_a_value():
    """A value written in the program would be the question's answer stated
    rather than produced, and would let the evaluator answer it with nothing
    run: a default and an assignment are both refused, naming the parameter."""

    class Defaulted(Filter):
        corner = Parameter("Hz", default=1.6 * kHz)

    class Assigned(Filter):
        def architecture(self):
            super().architecture()
            self.corner = 1.6 * kHz

    for system in (Defaulted, Assigned):
        result = elaborate(system, project_id=PROJECT)
        assert not result.ok
        (diagnostic,) = result.diagnostics
        assert diagnostic.code == diagnostics.SIM_QUESTION_RESULT
        assert "measures into corner" in diagnostic.message
        assert "1.6 kHz" in diagnostic.message


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


@pytest.mark.parametrize("statistic", [Average, Maximum, Minimum, PeakToPeak])
@pytest.mark.parametrize(
    "after, until", [(2 * ms, 1 * ms), (1 * ms, 1 * ms), (1 * ms, 500 * us)],
    ids=["reversed", "empty", "reversed across units"],
)
def test_a_window_whose_start_is_not_before_its_end_is_refused_where_it_is_written(statistic, after, until):
    """Lowered, it would be `FROM=2m TO=1m`: a measure the simulator takes
    over nothing, reported as though the run had failed. It is refused as an
    emulation count's reversed window is, with the same code and words."""
    with pytest.raises(FangError) as raised:
        statistic("outlet.line", after=after, until=until)
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == diagnostics.SIM_UNRESOLVED_SURFACE
    assert f"the {statistic.__name__} window ({after}, {until}) at outlet.line is empty" in diagnostic.message
    assert "its start is not before its end" in diagnostic.message
    assert diagnostic.location is not None and diagnostic.location.file == __file__
    # An ordered window still stands, and a one-sided one has nothing to order.
    statistic("outlet.line", after=500 * us, until=2 * ms)
    statistic("outlet.line", after=after)


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
    name: str = "ngspice"
    release: str = "ngspice-45.2"
    outputs: dict = field(default_factory=dict)

    def available(self) -> bool:
        return self.installed

    def version(self) -> str:
        if not self.installed:
            raise BackendUnavailable(f"{self.name} is not installed")
        return self.release

    def run(self, netlist, *, workspace, timeout=60):
        self.runs.append(netlist)
        return RawResult(
            self.name, self.release, self.stdout, self.exit_status, netlist,
            outputs=dict(self.outputs),
        )


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
    assert default_tools().names() == ["ngspice", "xyce", "kicad-erc", "touchstone"]
    assert isinstance(NGSPICE, Tool)
    assert isinstance(Spy("spy"), Tool)


def test_a_tool_registers_after_the_built_ins_or_before_a_tool_it_names():
    registry = default_tools()
    register_tool(Spy("late"), registry=registry)
    register_tool(Spy("early"), before="ngspice", registry=registry)
    assert registry.names() == ["early", "ngspice", "xyce", "kicad-erc", "touchstone", "late"]
    register_tool(Spy("late", level=Level.EXTERNAL), registry=registry)
    assert registry.names() == ["early", "ngspice", "xyce", "kicad-erc", "touchstone", "late"]
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


class TwoMeasures(Filter):
    """The filter, with a second measured parameter nothing constrains."""

    peak = Parameter("V", description="the output's peak, as measured")
    by_simulation = corner_question(
        measures={
            "corner": Crossing("outlet.line", level=707.1 * mV, edge="falling"),
            "peak": Maximum("outlet.line"),
        }
    )


def test_a_measure_nobody_took_is_not_decided_by_the_evaluator(tmp_path):
    """The corner is known and its constraints decided, but the peak has no
    value and no constraint: the evaluator cannot answer for a measure
    nobody took, so the question runs, and is unknown naming the peak while
    nothing measures it."""
    result, graph = graph_of(TwoMeasures)
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
    question = questions(graph.head)[0]
    assert set(constraint_statuses(graph.head, question).values()) == {CheckStatus.PASS}

    spy = Spy("spy")
    routed = route(graph.head, question, tools=ToolRegistry((spy,)))
    assert not routed.decided and routed.tool == "spy"
    outcome = answer(graph, question, tools=ToolRegistry((spy,)), workspace=tmp_path)
    assert spy.prepared == [question.id]
    assert outcome.result == "UNKNOWN"
    assert "peak" in outcome.message
    assert graph.head.entities[question.id].result == "UNKNOWN"


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

    class Unknown(Filter):
        by_simulation = corner_question(tool="spectre")

    snapshot = build(Named).snapshot
    routed = route(snapshot, questions(snapshot)[0])
    assert (routed.level, routed.tool) == (Level.CIRCUIT, "xyce")

    snapshot = build(Unknown).snapshot
    routed = route(snapshot, questions(snapshot)[0])
    assert not routed.routed and "spectre" in routed.reason


def test_method_routing_is_extended_by_registering_a_method(monkeypatch):
    from dataclasses import replace

    # Another module may already have registered the method; start without it.
    monkeypatch.delitem(METHOD_LEVELS, "emulation", raising=False)
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
    # As bytes, so the file is the same on every machine and its digest is the
    # digest of FOLLOWER; write_text would end Windows lines with \r\n.
    path.write_bytes(FOLLOWER.encode())
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


class Sensed(Follower):
    """The buffer with a second pin, AUX, that its model also takes as gnd."""

    aux = AnalogIn()
    AUX = Pin("AUX", role="analog", number="4")
    auxmap = PinMap({"aux.signal": "AUX", "aux.ref": "GND"})


def sensed(model: Path, aux: str | None):
    """The buffered filter with AUX wired to the ground or to the output, or
    left on no net."""

    class Wired(buffered(model, pin_map={"IN": "in", "OUT": "out", "GND": "gnd", "AUX": "gnd"})):
        buffer = Sensed()
        by_simulation = corner_question()

        def architecture(self):
            super().architecture()
            if aux == "ground":
                self.buffer.aux.signal >> self.buffer.signal_in.ref
            elif aux == "output":
                self.buffer.aux.signal >> self.c.p1

    return Wired


def test_pins_on_different_nets_landing_on_one_model_port_are_refused(follower):
    """GND and AUX both land on gnd. With AUX on the output net, an instance
    through GND alone simulated a circuit without AUX's connection; it is
    refused, naming the part, the port and the nets."""
    result = build(sensed(follower, "output"))
    with pytest.raises(NotRunnable) as raised:
        NGSPICE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits)
    assert raised.value.code == diagnostics.SIM_MODEL_PORT_UNREACHED
    message = str(raised.value)
    assert "U1's pin map lands AUX, GND on port gnd of follower" in message
    assert "different nets" in message
    from fang.netlist import compile_netlist

    netlist = compile_netlist(result.snapshot, traits=result.traits)
    nets = {(n.designator, n.pin): net.name for net in netlist.nets for n in net.nodes}
    assert f"AUX on {nets[('U1', 'AUX')]}" in message and f"GND on {nets[('U1', 'GND')]}" in message


def test_pins_on_one_node_landing_on_one_model_port_are_one_terminal(follower):
    """On the ground net with GND, AUX is the same node, and the instance is
    written through it; on no net, AUX carries nothing, and the port is
    reached through GND although AUX sorts first."""
    for aux in ("ground", None):
        result = build(sensed(follower, aux))
        deck = NGSPICE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits).input
        instance = next(line for line in deck.splitlines() if line.startswith("XU"))
        assert instance.split()[3] == "0", (aux, instance)


def declared_in(folder: Path, part: type) -> Part:
    """An instance of a part declared by a program in another folder, as a
    module of that folder's would declare it: its model's relative path is
    resolved there."""
    import importlib.util

    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "stage.py"
    path.write_text("def instance(part):\n    return part()\n")
    spec = importlib.util.spec_from_file_location(f"stage_{folder.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.instance(part)


def two_buffers(tmp_path, first: str, second: str):
    """The filter behind two buffers declared in folders a and b, each with
    its model at follower.sub beside it, holding the texts given."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "follower.sub").write_bytes(first.encode())
    (tmp_path / "b" / "follower.sub").write_bytes(second.encode())

    class Twice(Filter):
        left = declared_in(tmp_path / "a", Follower)
        right = declared_in(tmp_path / "b", Follower)
        by_simulation = corner_question()

        def __init__(self, **overrides):
            super().__init__(**overrides)
            for part in (self.left, self.right):
                part.add_trait(
                    Simulatable(
                        backends=("ngspice",), source="follower.sub",
                        pin_map={"IN": "in", "OUT": "out", "GND": "gnd"},
                    )
                )

        def architecture(self):
            self.inlet.line.signal >> self.left.signal_in.signal
            self.inlet.line.ref >> self.left.signal_in.ref
            self.left.signal_out.signal >> self.right.signal_in.signal
            self.left.signal_out.ref >> self.right.signal_in.ref
            self.right.signal_out.signal >> self.r.p1
            self.r.p2 >> self.c.p1
            self.c.p2 >> self.right.signal_out.ref
            self.outlet.line.signal >> self.c.p1
            self.outlet.line.ref >> self.c.p2

    return build(Twice)


def test_two_folders_naming_one_model_path_each_bring_their_own_file(tmp_path):
    """Two buffers declared in different folders name their models by one
    relative path, and the files differ. Named by the path alone they shared
    one bundle entry and one include, so one buffer ran the other's model;
    each is now named under its own digest, never under a machine's path."""
    other = FOLLOWER.replace("follower", "follower_b").replace("1e9", "1e6")
    result = two_buffers(tmp_path, FOLLOWER, other)
    job = NGSPICE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits)

    def digest(text: str) -> str:
        return "sha256:" + hashlib.sha256(text.encode()).hexdigest()

    named = {f"{digest(text)[7:19]}/follower.sub": digest(text) for text in (FOLLOWER, other)}
    assert job.inputs == named
    for path in named:
        assert f".include {path}" in job.input
        assert job.sources[path] == str(tmp_path / ("a" if named[path] == digest(FOLLOWER) else "b") / "follower.sub")
    instances = sorted(line.split()[-1] for line in job.input.splitlines() if line.startswith("XU"))
    assert instances == ["follower", "follower_b"]
    assert str(tmp_path) not in job.input and str(tmp_path) not in canonical_dumps(job.manifest())


def test_one_model_file_named_twice_is_one_entry(tmp_path):
    result = two_buffers(tmp_path, FOLLOWER, FOLLOWER)
    job = NGSPICE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits)
    assert job.inputs == {"follower.sub": "sha256:" + hashlib.sha256(FOLLOWER.encode()).hexdigest()}
    assert job.input.count(".include") == 1


def test_two_model_files_declaring_one_subcircuit_are_refused(tmp_path):
    """A deck holds one definition of a subcircuit: ngspice warns of the
    second and ignores it, so both parts would run the first file's model."""
    result = two_buffers(tmp_path, FOLLOWER, FOLLOWER.replace("1e9", "1e6"))
    with pytest.raises(NotRunnable) as raised:
        NGSPICE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits)
    message = str(raised.value)
    assert "two different model files declare subcircuit follower" in message
    assert "U1 from " in message and "U2 from " in message


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
    lines = NgspiceDialect().analysis_lines(Transient(stop="1.2ms", step="10ns"), [measure])
    assert lines == [
        ".control",
        "tran 10ns 1.2ms",
        "let fang_s0 = v(5)-v(4)",
        "meas tran fang_m0 PP fang_s0 from=0.001 to=0.0012",
        ".endc",
    ]
    held = DeckMeasure("fang_m0", "value_at", "5")
    assert NgspiceDialect().analysis_lines(OperatingPoint(), [held])[2:4] == [
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


def test_a_run_that_does_not_complete_leaves_the_result_unknown_with_its_evidence(tmp_path):
    """A failed run is data: its evidence records why nothing was measured,
    the verification stays UNKNOWN, and no parameter is set."""

    class Crashing(CannedBackend):
        def run(self, netlist, *, workspace, timeout=60):
            raise RuntimeError("the simulator crashed")

    result, graph = graph_of()
    tool = SpiceTool("ngspice", NgspiceDialect(), Crashing())
    outcome = answer(
        graph, questions(graph.head)[0], traits=result.traits, tools=ToolRegistry((tool,)),
        workspace=tmp_path, record_time=FIXED_TIME,
    )
    assert outcome.status == ANSWERED and outcome.result == "UNKNOWN"
    record = graph.head.entities[outcome.evidence].extensions["measurement"]
    assert record["status"] == "failed"
    assert "the simulator crashed" in record["measures"][0]["reason"]
    assert not graph.head.entities[SYSTEM].parameters["corner"].known
    assert graph.head.entities[outcome.question.id].evidence == (outcome.evidence,)

    # A run that did not complete is tried again, as evidence of its own.
    retried = answer(
        graph, questions(graph.head)[0], traits=result.traits, tools=ToolRegistry((tool,)),
        workspace=tmp_path, record_time=FIXED_TIME,
    )
    assert retried.status == ANSWERED and retried.evidence != outcome.evidence
    assert outcome.evidence in graph.head.entities


def test_a_tool_gone_at_run_time_is_unsupported_and_records_nothing(tmp_path):
    """Installed when asked, gone when run: reported unsupported, by name."""
    from fang.verification import ToolUnavailable

    result, graph = graph_of()
    tool = SpiceTool("ngspice", NgspiceDialect(), CannedBackend())

    def vanish(job, *, workspace):
        raise ToolUnavailable("ngspice is not installed any more")

    tool.run = vanish
    before = graph.head.hash
    outcome = answer(
        graph, questions(graph.head)[0], traits=result.traits, tools=ToolRegistry((tool,)),
        workspace=tmp_path,
    )
    assert outcome.status == UNSUPPORTED and "not installed any more" in outcome.message
    assert graph.head.hash == before


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


# -- Xyce ----------------------------------------------------------------------

#: A measure file in the form the Xyce Reference Guide documents for `.MEASURE`
#: output: one `NAME = value` line per measure, `FAILED` for one that could not
#: be taken. Xyce is not installed where this was written, so it is written from
#: the guide rather than captured from a run.
XYCE_MEASURE_FILE = """FANG_M0 = 1.591550e+03
FANG_M1 = FAILED
"""


def xyce(**kwargs):
    backend = CannedBackend(
        "", name="xyce", release="Xyce Release 7.8",
        outputs={"deck.cir.ma0": XYCE_MEASURE_FILE}, **kwargs,
    )
    tool = SpiceTool("xyce", XyceDialect(), backend)
    return tool, ToolRegistry((NGSPICE, tool))


def test_the_ngspice_and_xyce_decks_share_their_circuit():
    """Devices, instances and bench are identical; only each simulator's own
    options, analysis and measurement lines differ."""
    class Loaded(Filter):
        by_simulation = corner_question(loads={"outlet.line": 10 * kOhm})

    result = build(Loaded)
    question = questions(result.snapshot)[0]
    spice = NGSPICE.prepare(result.snapshot, question, traits=result.traits).input.splitlines()
    other = XYCE.prepare(result.snapshot, question, traits=result.traits).input.splitlines()

    def circuit(lines):
        return lines[: next(i for i, line in enumerate(lines) if line.lower().startswith(".options"))]

    assert circuit(spice) == circuit(other)
    assert any(line.startswith("Rfang_load0 ") for line in circuit(spice))
    assert spice[len(circuit(spice)):] != other[len(circuit(other)):]
    assert other[-1] == ".end"


def test_the_xyce_dialect_writes_deck_level_measure_lines():
    window = DeckMeasure(
        "fang_m0", "peak_to_peak", "5", "4", after=Decimal("0.001"), until=Decimal("0.0012")
    )
    assert XyceDialect().analysis_lines(Transient(stop="1.2ms", step="10ns"), [window]) == [
        ".tran 10ns 1.2ms",
        ".MEASURE TRAN fang_m0 PP V(5,4) FROM=0.001 TO=0.0012",
    ]
    corner = DeckMeasure("fang_m0", "crossing", "1", level=Decimal("0.7071"), edge="falling")
    sweep = ACSweep(variation="dec", points=100, start="10", stop="1meg")
    assert XyceDialect().analysis_lines(sweep, [corner])[1] == (
        ".MEASURE AC fang_m0 WHEN VM(1)=0.7071 FALL=1"
    )
    assert XyceDialect().options({"reltol": "1e-3", "abstol": "1e-12", "method": "gear", "vntol": "1e-6"}) == [
        ".OPTIONS TIMEINT ABSTOL=1e-12 METHOD=gear RELTOL=1e-3",
        "* vntol=1e-6 has no Xyce option and is not written",
    ]
    with pytest.raises(SimulationError, match="operating_point"):
        XyceDialect().analysis_lines(OperatingPoint(), [DeckMeasure("fang_m0", "value_at", "5")])


def test_the_xyce_measure_file_is_read_into_decimals_and_nothing_else():
    slots = [DeckMeasure(f"fang_m{i}", "crossing", "") for i in range(3)]
    found = XyceDialect().parse("", slots, outputs={"deck.cir.ma0": XYCE_MEASURE_FILE})
    assert found["fang_m0"] == Decimal("1591.550")
    assert found["fang_m1"] == "Xyce reported the measure as failed"
    assert found["fang_m2"] == "Xyce's measure file does not report it"
    # What Xyce prints is not where it reports measures.
    printed = XyceDialect().parse("FANG_M0 = 2", slots[:1], outputs={})
    assert printed["fang_m0"] == "Xyce's measure file does not report it"


def test_a_xyce_run_is_read_into_measurements_with_its_version(tmp_path):
    result = build(Floored)
    tool, _ = xyce()
    question = questions(result.snapshot)[0]
    job = tool.prepare(result.snapshot, question, traits=result.traits)
    corner, floor = tool.read(job, tool.run(job, workspace=tmp_path))
    assert corner.quantity == Quantity.scalar("1591.55", "Hz")
    assert (corner.tool, corner.version) == ("xyce", "Xyce Release 7.8")
    assert floor.quantity is None and "failed" in floor.reason


def test_xyce_reports_unsupported_by_name_where_it_is_absent(tmp_path):
    class Named(Filter):
        by_simulation = corner_question(tool="xyce")

    result, graph = graph_of(Named)
    absent = SpiceTool("xyce", XyceDialect(), XyceBackend(executable="definitely-not-xyce"))
    outcome = answer(
        graph, questions(graph.head)[0], traits=result.traits,
        tools=ToolRegistry((NGSPICE, absent)), workspace=tmp_path,
    )
    assert outcome.status == UNSUPPORTED
    assert "xyce is not installed" in outcome.message
    with pytest.raises(BackendUnavailable, match="definitely-not-xyce"):
        absent.backend.run("* deck", workspace=tmp_path)
    assert not absent.covers(replace_bench(questions(graph.head)[0], "operating_point"))


def replace_bench(question, kind):
    """The same question over another kind of analysis."""
    from dataclasses import replace

    bench = dict(question.data["bench"], analysis={"kind": kind, "probes": []})
    return replace(question, data={**question.data, "bench": bench})


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
    assert (record["status"], record["ran"]) == ("succeeded", "local")
    assert record["confidence"] == "0.5"
    assert record["measures"] == [
        {"name": "corner", "parameter": f"{SYSTEM}.corner", "unit": "Hz", "value": "1591.612"}
    ]
    assert "a 1 V supply at inlet.line" in record["assumptions"]
    assert "system.inlet is abstracted, not modelled" in record["coverage_gaps"]
    digest = "sha256:" + hashlib.sha256(FOLLOWER.encode()).hexdigest()
    assert record["inputs"] == [{"path": "models/follower.sub", "hash": digest}]


def test_every_record_says_where_its_run_happened(tmp_path):
    """RFC 3's record carries `ran` for every tool: local unless the tool's
    job says it was hosted, once, as the record's own field, and nothing
    else."""
    from fang.verification import measurement_record

    result = build()
    question = questions(result.snapshot)[0]
    raw = RawRun("spy", "spy-1", 0)

    def record(**extra):
        job = Job.single("spy", question, result.snapshot.hash, "input.txt", "spy", extra=extra)
        return measurement_record(job, raw, (), Level.CIRCUIT)

    assert record()["ran"] == "local"
    hosted = record(ran="hosted", seed="7")
    assert (hosted["ran"], hosted["seed"]) == ("hosted", "7")
    with pytest.raises(ValueError, match="ran"):
        record(ran="somewhere")
    with pytest.raises(ValueError, match="status"):
        record(status="PASS")


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


def _carried_into(system, graph):
    """A fresh elaboration of another program, with what the graph's runs
    measured carried in, as a rebuild into the workspace would give."""
    return KernelGraph(
        carry_measurements(build(system).snapshot, MeasuredFacts.of(graph.head)),
        checks=DEFAULT_CHECKS,
    )


def _evidence_count(snapshot) -> int:
    return sum(1 for e in snapshot.entities.values() if e.kind == "evidence" and "measurement" in e.extensions)


def test_a_recorded_failure_re_enters_when_its_constraint_is_relaxed(tmp_path):
    """The same job on the same version is not run again, and its recorded
    measurements re-enter through the gate: the FAIL a tightened constraint
    left stands while the constraint does, and passes once it is relaxed,
    on the same evidence, with nothing run."""
    graph, failed = answered(tmp_path, Tightened)
    assert failed.status == FAILED
    tool, tools = canned()
    history = len(graph.history)

    again = answer(graph, failed.question, tools=tools, workspace=tmp_path, record_time=FIXED_TIME)
    assert (again.status, again.result) == ("current", "FAIL")
    assert len(graph.history) == history and tool.backend.runs == []

    relaxed = _carried_into(Filter, graph)
    question = questions(relaxed.head)[0]
    assert relaxed.head.entities[question.id].result == "FAIL"
    outcome = answer(relaxed, question, tools=tools, workspace=tmp_path, record_time=FIXED_TIME)
    assert (outcome.status, outcome.result) == (ANSWERED, "PASS")
    assert "re-entered through the gate" in outcome.message
    assert tool.backend.runs == []
    assert _evidence_count(relaxed.head) == 1
    value = relaxed.head.entities[SYSTEM].parameters["corner"]
    assert value.source == failed.evidence and value.quantity == Quantity.scalar("1591.612", "Hz")
    verification = relaxed.head.entities[question.id]
    assert verification.evidence == (failed.evidence,)
    assert verification.provenance.records[-1].activity == "verification_reentry"


def test_a_carried_pass_a_tightened_constraint_breaks_is_carried_as_the_failure(tmp_path):
    """Rebuilt under a constraint tightened since, a current measurement that
    breaks it is not carried into the design: its verification is carried
    as FAIL with its evidence, and the parameter without a value, which is
    exactly what the failure-recording transaction leaves when the same run
    meets the tightened constraint at re-entry. The design passes the gate."""
    graph, passed = answered(tmp_path)
    assert passed.result == "PASS"

    tightened = carry_measurements(build(Tightened).snapshot, MeasuredFacts.of(graph.head))
    verification = verification_of(tightened)
    assert verification.result == "FAIL" and verification.evidence == (passed.evidence,)
    assert passed.evidence in tightened.entities
    assert not tightened.entities[SYSTEM].parameters["corner"].known
    assert all(not record.fields for record in tightened.entities[SYSTEM].provenance.records)
    assert KernelGraph(tightened, checks=DEFAULT_CHECKS).propose(
        Transaction(tightened.hash, ())
    ).accepted

    recorded, failed = answered(tmp_path / "again", Tightened)
    assert failed.status == FAILED
    assert canonical_dumps(verification.as_dict()) == canonical_dumps(
        recorded.head.entities[failed.question.id].as_dict()
    )

    # Unchanged, the program carries its PASS and its value as before.
    kept = carry_measurements(build().snapshot, MeasuredFacts.of(graph.head))
    assert verification_of(kept).result == "PASS" and kept.entities[SYSTEM].parameters["corner"].known


class Coupled(Filter):
    """The filter, its corner now also held below a limit nobody has set."""

    limit = Parameter("Hz", description="a limit with no value yet")

    def constraints(self):
        super().constraints()
        require(self.corner <= self.limit)


def test_a_recorded_pass_whose_constraint_becomes_undecided_is_not_current(tmp_path):
    graph, passed = answered(tmp_path)
    assert passed.result == "PASS"
    tool, tools = canned()

    coupled = _carried_into(Coupled, graph)
    question = questions(coupled.head)[0]
    assert coupled.head.entities[question.id].result == "PASS"
    outcome = answer(coupled, question, tools=tools, workspace=tmp_path, record_time=FIXED_TIME)
    assert (outcome.status, outcome.result) == (ANSWERED, "UNKNOWN")
    assert coupled.head.entities[question.id].result == "UNKNOWN"
    assert tool.backend.runs == [] and _evidence_count(coupled.head) == 1


def test_an_unrelated_rejection_records_nothing(tmp_path):
    graph, outcome = answered(
        tmp_path, policy=Policy(approvals_required=frozenset({"lead engineer"}))
    )
    assert outcome.status == REJECTED
    assert len(graph.history) == 1
    assert not any(e.kind == "evidence" and "measurement" in e.extensions
                   for e in graph.head.entities.values())


# -- a record that changes an entity names what it changed (RFC 3 section 14) --

ANSWERED_FIELDS = ("evidence", "level", "result", "tool")
CORNER_VALUE = ("parameters.corner.value",)


def appended(before, after) -> dict[str, list]:
    """The provenance records `after` holds on each entity `before` already
    held, beyond those it held there; what was there is never rewritten."""
    out = {}
    for entity_id, entity in after.entities.items():
        was = before.entities.get(entity_id)
        if was is None:
            continue
        old, new = was.provenance.records, entity.provenance.records
        assert new[: len(old)] == old
        if len(new) > len(old):
            out[entity_id] = list(new[len(old):])
    return out


def named(records: dict[str, list]) -> dict[str, list]:
    return {entity_id: [(r.activity, r.fields) for r in chain] for entity_id, chain in records.items()}


def test_a_run_names_the_measured_value_and_the_answer_it_set(tmp_path):
    """The run's record is appended to the part whose parameter it set,
    naming the measured value apart from the parameter, and to the
    verification, naming the facts of the answer; the evidence it creates
    names nothing, since a creating record covers everything."""
    graph, outcome = answered(tmp_path)
    assert named(appended(graph.history[0], graph.head)) == {
        SYSTEM: [("verification_run", CORNER_VALUE)],
        outcome.question.id: [("verification_run", ANSWERED_FIELDS)],
    }
    record = graph.head.entities[SYSTEM].provenance.records[-1]
    assert record.actor.id == "ngspice" and record.derived_from == (outcome.question.id,)
    serialized = json.loads(canonical_dumps(graph.head.entities[SYSTEM].as_dict()))
    assert serialized["provenance"][-1]["fields"] == ["parameters.corner.value"]
    assert graph.head.entities[outcome.evidence].provenance.records[-1].fields == ()


def test_a_recorded_failure_names_only_the_answer(tmp_path):
    """The failure sets no parameter, so no part gains a record."""
    graph, outcome = answered(tmp_path, Tightened)
    assert outcome.status == FAILED
    assert named(appended(graph.history[0], graph.head)) == {
        outcome.question.id: [("verification_run", ANSWERED_FIELDS)],
    }


def test_a_re_entered_run_and_an_equation_level_answer_name_their_fields(tmp_path):
    graph, failed = answered(tmp_path, Tightened)
    relaxed = _carried_into(Filter, graph)
    before = relaxed.head
    tool, tools = canned()
    outcome = answer(relaxed, questions(before)[0], tools=tools, workspace=tmp_path, record_time=FIXED_TIME)
    assert outcome.status == ANSWERED
    assert named(appended(before, relaxed.head)) == {
        SYSTEM: [("verification_reentry", CORNER_VALUE)],
        failed.question.id: [("verification_reentry", ANSWERED_FIELDS)],
    }

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
    before = graph.head
    decided = answer(graph, questions(before)[0], tools=ToolRegistry(()), workspace=tmp_path)
    assert decided.status == DECIDED
    assert named(appended(before, graph.head)) == {
        decided.question.id: [("equation_check", ANSWERED_FIELDS)],
    }


def test_a_records_fields_are_sorted_and_read_back():
    record = ProvenanceRecord(
        ProvenanceOrigin.GENERATED, "verification_run", Actor(ActorKind.TOOL, "ngspice", "45.2"),
        "REV-000001", FIXED_TIME, fields=("tool", "result", "evidence", "result"),
    )
    assert record.fields == ("evidence", "result", "tool")
    assert record.as_dict()["fields"] == ["evidence", "result", "tool"]
    assert ProvenanceRecord.from_dict(json.loads(canonical_dumps(record.as_dict()))) == record
    unnamed = ProvenanceRecord(
        ProvenanceOrigin.GENERATED, "elaboration", Actor(ActorKind.TOOL, "fang"), "REV-000001", FIXED_TIME,
    )
    assert "fields" not in unnamed.as_dict()


def test_a_rebuild_carries_the_record_that_set_a_measured_value(tmp_path):
    """Carried onto a fresh elaboration, a measured value brings the record
    that set it, after the program's own; a value not carried brings none."""
    graph, outcome = answered(tmp_path)
    records = read_record_stream(canonical_record_stream(graph.head.records()))
    rebuilt = carry_measurements(build().snapshot, MeasuredFacts.from_records(records))
    chain = rebuilt.entities[SYSTEM].provenance.records
    assert [r.fields for r in chain][-1] == CORNER_VALUE
    assert chain[:-1] == build().snapshot.entities[SYSTEM].provenance.records

    retuned = carry_measurements(build(Retuned).snapshot, MeasuredFacts.from_records(records))
    assert all(not r.fields for r in retuned.entities[SYSTEM].provenance.records)


# -- condition 5 excepts a question's measured parameters while it awaits ----


def served(system=Filter):
    """The program elaborated, with its constraints serving its requirement so
    that a policy can mark the requirement must-be-decided. `require` names no
    requirement, so the test sets it."""
    from dataclasses import replace

    from fang.constraints import Constraint

    result = build(system)
    requirement = next(
        e.id for e in result.snapshot.entities.values() if isinstance(e, Requirement)
    )
    entities = {
        key: replace(entity, source=requirement) if isinstance(entity, Constraint) else entity
        for key, entity in result.snapshot.entities.items()
    }
    return result, result.snapshot.with_entities(entities, result.snapshot.revision_id), requirement


def first_commit(snapshot, policy):
    """The program proposed onto an empty head in one transaction, as a first
    elaboration is: the transaction that declares the question."""
    from fang.graph import AddEntity

    graph = KernelGraph(snapshot.with_entities({}, "REV-000000"), checks=DEFAULT_CHECKS, policy=policy)
    operations = tuple(
        AddEntity(entity=entity, reason="elaborated")
        for entity in sorted(snapshot.entities.values(), key=lambda e: e.id)
    )
    return graph.propose(Transaction(graph.head.hash, operations))


def test_declaring_an_unanswered_question_does_not_block_a_must_be_decided_requirement():
    _, snapshot, requirement = served()
    proposal = first_commit(snapshot, Policy(must_be_decided=frozenset({requirement})))
    # The constraints over the measured parameter are run and still undecided.
    undecided = [r for r in proposal.checks if r.check == "constraint"]
    assert len(undecided) == 2 and {r.status for r in undecided} == {CheckStatus.UNKNOWN}
    assert proposal.accepted, [d.message for d in proposal.diagnostics]


def test_an_undecided_constraint_over_an_ordinary_parameter_still_blocks():
    from fang.constraints import Constraint, le

    _, snapshot, requirement = served()
    ordinary = Constraint(
        authored("RULE-GAIN"),
        constraint_kind="gain",
        targets=(SYSTEM,),
        expression=le(Ref(SYSTEM, "gain"), Literal.of(10)),
        source=requirement,
    )
    entities = dict(snapshot.entities)
    entities[ordinary.id] = ordinary
    proposal = first_commit(
        snapshot.with_entities(entities, snapshot.revision_id),
        Policy(must_be_decided=frozenset({requirement})),
    )
    assert proposal.rejected
    blocked = [d for d in proposal.diagnostics if d.code == diagnostics.TXN_UNDECIDED_BLOCKED]
    # Only the ordinary one: the measured constraints are still excepted.
    assert [d.entities[0] for d in blocked] == ["RULE-GAIN"]


def test_recording_a_failed_verification_is_not_blocked_by_what_it_leaves_undecided(tmp_path):
    result, snapshot, requirement = served(Tightened)
    policy = Policy(
        required_checks=frozenset({"constraint"}), must_be_decided=frozenset({requirement})
    )
    graph = KernelGraph(snapshot, checks=DEFAULT_CHECKS, policy=policy)
    _, tools = canned()
    outcome = answer(
        graph, questions(graph.head)[0], traits=result.traits, tools=tools,
        workspace=tmp_path, record_time=FIXED_TIME,
    )
    assert outcome.status == FAILED, outcome.message
    assert graph.head.entities[outcome.question.id].result == "FAIL"
    assert "set_parameter" not in [op.op for op in outcome.recorded.transaction.operations]
    # The constraints stay undecided on the head, which is true: the design has
    # no accepted value for them.
    assert set(constraint_statuses(graph.head, outcome.question).values()) == {CheckStatus.UNKNOWN}


def test_a_run_that_measures_nothing_is_recorded_under_a_must_be_decided_requirement(tmp_path):
    # The run reports no corner, so it answers UNKNOWN and sets no parameter.
    # The verification's own result states the constraints it leaves
    # undecided; condition 5 does not, or the run could never be recorded.
    result, snapshot, requirement = served()
    policy = Policy(
        required_checks=frozenset({"constraint"}), must_be_decided=frozenset({requirement})
    )
    graph = KernelGraph(snapshot, checks=DEFAULT_CHECKS, policy=policy)
    _, tools = canned(FILTER_OUTPUT.replace("fang_m0             =  1.591612e+03\n", ""))
    outcome = answer(
        graph, questions(graph.head)[0], traits=result.traits, tools=tools,
        workspace=tmp_path, record_time=FIXED_TIME,
    )
    assert outcome.status == ANSWERED and outcome.result == "UNKNOWN", outcome.message
    assert len(graph.history) == 2
    assert graph.head.entities[outcome.question.id].evidence == (outcome.evidence,)
    assert not graph.head.entities[SYSTEM].parameters["corner"].known


class TwoQuestions(Filter):
    """One constraint over two parameters, each measured by its own question.

    Whichever runs first leaves the constraint undecided for the other's
    parameter; if condition 5 blocked that, neither could ever be answered.
    """

    corner_again = Parameter("Hz", description="the same corner, measured again")
    again = corner_question(
        measures={"corner_again": Crossing("outlet.line", level=707.1 * mV, edge="falling")}
    )

    def constraints(self):
        super().constraints()
        require(self.corner_again <= self.corner + 1 * kHz)


def test_two_questions_measuring_into_one_constraint_are_both_answered(tmp_path):
    result, snapshot, requirement = served(TwoQuestions)
    policy = Policy(
        required_checks=frozenset({"constraint"}), must_be_decided=frozenset({requirement})
    )
    graph = KernelGraph(snapshot, checks=DEFAULT_CHECKS, policy=policy)
    _, tools = canned()
    outcomes = verify(graph, traits=result.traits, tools=tools, workspace=tmp_path,
                      record_time=FIXED_TIME)
    assert [o.status for o in outcomes] == [ANSWERED, ANSWERED], [o.message for o in outcomes]
    # The first re-entry left the shared constraint undecided for the other
    # question's parameter and was not blocked; the second decided it.
    assert outcomes[0].result == "UNKNOWN" and outcomes[1].result == "PASS"
    assert len(graph.history) == 3
    held = graph.head.entities[SYSTEM].parameters
    assert held["corner"].known and held["corner_again"].known


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


class Retuned(Filter):
    """The same filter and question, with a 22 kOhm resistor: its corner is
    723 Hz, not the 1.59 kHz measured on the 10 kOhm one."""

    r = Resistor(resistance=22 * kOhm)


def test_a_measurement_of_a_changed_circuit_is_not_carried(tmp_path):
    """The question is the same, so its description is too; the circuit it
    lowers to is not. Preparing it afresh gives another job, so the old
    measurement is not current and the question is answered again."""
    graph, outcome = answered(tmp_path)
    facts = MeasuredFacts.of(graph.head)

    kept = carry_measurements(build().snapshot, facts)
    assert verification_of(kept).result == "PASS"
    assert kept.entities[SYSTEM].parameters["corner"].known

    rebuilt = carry_measurements(build(Retuned).snapshot, facts)
    assert verification_of(rebuilt).result == "UNKNOWN"
    assert not rebuilt.entities[SYSTEM].parameters["corner"].known
    assert outcome.evidence not in rebuilt.entities
    # Routed on the carried head, the question runs rather than being decided.
    assert not route(rebuilt, questions(rebuilt)[0]).decided


def test_a_changed_model_file_makes_its_measurement_stale(tmp_path, follower):
    """A model file is not in the snapshot; its digest is in the job."""
    graph, outcome = answered(tmp_path, buffered(follower))
    facts = MeasuredFacts.of(graph.head)
    result = build(buffered(follower))
    kept = carry_measurements(result.snapshot, facts, traits=result.traits)
    assert kept.entities[SYSTEM].parameters["corner"].known

    follower.write_bytes(FOLLOWER.replace("Rin in gnd 1e9", "Rin in gnd 1e6").encode())
    result = build(buffered(follower))
    rebuilt = carry_measurements(result.snapshot, facts, traits=result.traits)
    assert verification_of(rebuilt).result == "UNKNOWN"
    assert not rebuilt.entities[SYSTEM].parameters["corner"].known


@dataclass
class Untouchable:
    """A backend that fails the test if anything asks it a question."""

    name: str = "ngspice"

    def available(self) -> bool:
        raise AssertionError("currency consulted whether the tool is installed")

    def version(self) -> str:
        raise AssertionError("currency consulted the installed version")

    def run(self, netlist, *, workspace, timeout=60):
        raise AssertionError("currency ran the tool")


def test_currency_rests_on_the_job_and_not_on_this_machine(tmp_path):
    """Whether a measurement is kept is the same on every machine: it is the
    job's hash, which preparation gives, and never whether the tool is
    installed here or which version is."""
    graph, outcome = answered(tmp_path)
    untouchable = ToolRegistry((SpiceTool("ngspice", NgspiceDialect(), Untouchable()),))
    kept = carry_measurements(build().snapshot, MeasuredFacts.of(graph.head), tools=untouchable)
    assert kept.hash == carry_measurements(build().snapshot, MeasuredFacts.of(graph.head)).hash
    assert kept.entities[SYSTEM].parameters["corner"].known
    assert verification_of(kept).result == "PASS"


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


#: The same filter with a modelled buffer in front of it, appended to the
#: program and named with --system; its model is follower.sub beside it.
BUFFERED = '''

from fang.interfaces import AnalogIn
from fang.traits import Simulatable


class Follower(Part):
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


class Buffered(Filter):
    buffer = Follower()

    def __init__(self, **overrides):
        super().__init__(**overrides)
        self.buffer.add_trait(
            Simulatable(
                backends=("ngspice",),
                source="follower.sub",
                pin_map={"IN": "in", "OUT": "out", "GND": "gnd"},
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
'''

#: The system block of a program the command elaborates, under its default project.
LOCAL_SYSTEM = derive("PRJ-LOCAL", "block", "system").id


def program(
    tmp_path, *, upper: str = "2", supplies: str = '{"inlet.line": 1 * V}', extra: str = ""
) -> str:
    path = tmp_path / "filter.py"
    path.write_text(PROGRAM.replace("@UPPER@", upper).replace("@SUPPLIES@", supplies) + extra)
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


def test_verify_commit_refuses_a_program_changed_since_its_build(tmp_path, ngspice, capsys):
    """--commit persists measurements and nothing else. A resistor retuned
    since the last build is an edit to the design, which verify committed
    with its new measurement, past build's tool plan; it is refused before
    anything runs, naming build, and after a build the commit goes through."""
    source = program(tmp_path)
    workspace = Workspace(tmp_path)
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    committed = snapshot_of(workspace.dir)
    runs = len(ngspice.runs)
    capsys.readouterr()

    # A different length as well as a different value: a program rewritten
    # within the second at the same size could be read from stale bytecode.
    path = Path(source)
    path.write_text(path.read_text().replace("10 * kOhm)", "22 * kOhm)  # retuned"))
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_FAILED
    captured = capsys.readouterr()
    assert "--commit persists measurements and nothing else" in captured.err
    assert "filter.py no longer elaborates to the design in" in captured.err
    assert "run 'fang build' first" in captured.err
    assert captured.out == ""
    assert snapshot_of(workspace.dir) == committed
    assert len(ngspice.runs) == runs

    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    assert len(ngspice.runs) == runs + 1
    assert "22k" in ngspice.runs[-1] or "22000" in ngspice.runs[-1]


def test_a_constraint_tightened_since_a_pass_is_recorded_as_its_failure(tmp_path, ngspice, capsys):
    """A PASS committed at 1.59 kHz under a 2 kHz limit, and the limit then
    tightened to 1.2 kHz. The tightening is an edit, so verify --commit
    refuses it and writes nothing, and build persists it. The measurement is
    still current and breaks the new limit, so it does not reach the design
    (RFC 12 section 12.9): build records the verification as FAIL with its
    evidence and the corner without a value, as the failure-recording
    transaction does, rather than refusing the design and leaving the
    workspace stuck. Nothing runs again, and relaxing the limit gives the
    recorded run's PASS back."""
    source = program(tmp_path)
    workspace = Workspace(tmp_path)
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    committed = snapshot_of(workspace.dir)
    runs = len(ngspice.runs)
    capsys.readouterr()

    def persisted():
        records = workspace.read_records()
        verification = next(r for r in records if r["kind"] == "verification" and "question" in r.get("extensions", {}))
        corner = next(r for r in records if r["id"] == LOCAL_SYSTEM)["parameters"]["corner"]
        return verification, corner

    passed, _ = persisted()
    program(tmp_path, upper="1.2")
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_FAILED
    assert "run 'fang build' first" in capsys.readouterr().err
    assert snapshot_of(workspace.dir) == committed

    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    verification, corner = persisted()
    assert verification["result"] == "FAIL"
    assert verification["evidence"] == passed["evidence"]
    assert corner["status"] == "unknown"
    capsys.readouterr()

    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_FAILED
    output = capsys.readouterr().out
    assert "current: this run is already recorded" in output
    assert output.rstrip().splitlines()[-2:] == ["  FAIL", "nothing new to commit"]
    assert len(ngspice.runs) == runs
    assert persisted()[0]["result"] == "FAIL"

    program(tmp_path, upper="2")
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    verification, corner = persisted()
    assert verification["result"] == "PASS" and corner["status"] == "inferred"
    assert len(ngspice.runs) == runs


def test_verify_commits_only_what_the_gate_accepts(tmp_path, ngspice, capsys, monkeypatch):
    """What --commit persists passes the gate whole first, as what build
    persists does: a design the gate refuses is reported with the gate's
    diagnostics and not written."""
    import fang.cli
    from fang.diagnostics import Diagnostic, Severity

    source = program(tmp_path)
    workspace = Workspace(tmp_path)
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    built = snapshot_of(workspace.dir)
    capsys.readouterr()

    @dataclass
    class Refused:
        rejected: bool = True
        diagnostics: tuple = (
            Diagnostic(diagnostics.TXN_GATE_BLOCKED, Severity.ERROR, "the gate says no"),
        )

    seen = []
    monkeypatch.setattr(fang.cli, "_gated", lambda snapshot, reason: seen.append(snapshot) or Refused())
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_FAILED
    captured = capsys.readouterr()
    assert f"{diagnostics.TXN_GATE_BLOCKED}: the gate says no" in captured.err
    assert "the commit gate rejected the verified design; nothing is committed" in captured.err
    assert len(seen) == 1 and seen[0].entities[LOCAL_SYSTEM].parameters["corner"].known
    assert snapshot_of(workspace.dir) == built


def test_a_stale_model_runs_again_and_its_answer_is_committed(tmp_path, ngspice, capsys):
    """A model file is read by the program and is not the program: the
    measurement made on the old file is no longer current, and --commit runs
    the question again and commits its answer rather than asking for a build."""
    source = program(tmp_path, extra=BUFFERED)
    model = tmp_path / "follower.sub"
    model.write_bytes(FOLLOWER.encode())
    workspace = Workspace(tmp_path)
    command = [source, "--system", "Buffered", "-C", str(tmp_path)]
    assert main(["build", *command]) == EXIT_OK
    assert main(["verify", *command, "--commit"]) == EXIT_OK
    first = workspace.read_manifest().snapshot
    runs = len(ngspice.runs)
    capsys.readouterr()

    changed = FOLLOWER.replace("Rin in gnd 1e9", "Rin in gnd 1e6").encode()
    model.write_bytes(changed)
    assert main(["verify", *command, "--commit"]) == EXIT_OK
    captured = capsys.readouterr()
    assert "run 'fang build' first" not in captured.err
    assert "  circuit level, ngspice (ngspice-45.2)" in captured.out
    assert len(ngspice.runs) == runs + 1
    assert workspace.read_manifest().snapshot != first
    digest = "sha256:" + hashlib.sha256(changed).hexdigest()
    (evidence,) = [
        record for record in workspace.read_records()
        if record["kind"] == "evidence" and "measurement" in record.get("extensions", {})
    ]
    assert evidence["extensions"]["measurement"]["inputs"] == [{"path": "follower.sub", "hash": digest}]


def test_evidence_a_retried_run_left_behind_is_not_a_change(tmp_path, ngspice, capsys):
    """A run that did not complete is tried again as evidence of its own, and
    the first attempt's evidence stays on the head uncited. That is a run's
    leftover, not an edit to the program, so the next --commit goes through."""
    source = program(tmp_path)
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    ngspice.exit_status = 1
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    ngspice.exit_status = 0
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    records = Workspace(tmp_path).read_records()
    runs = [r for r in records if r["kind"] == "evidence" and "measurement" in r.get("extensions", {})]
    assert len(runs) == 2
    capsys.readouterr()

    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    captured = capsys.readouterr()
    assert "run 'fang build' first" not in captured.err
    assert "equation level, by the constraint evaluator; nothing runs" in captured.out


def test_staleness_is_judged_on_the_committed_runs_beside_the_design(tmp_path, ngspice, monkeypatch):
    """verify names a run on a since-rebuilt firmware as stale, from what was
    committed. The firmware is found beside the program that declares the
    part it runs on, so the parts stay in what is judged; with the runs alone,
    every firmware read as missing from any other directory."""
    import fang.emulation

    judged = []
    monkeypatch.setattr(fang.emulation, "stale", lambda snapshot: judged.append(snapshot) or ())
    source = program(tmp_path)
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    assert main(["verify", source, "-C", str(tmp_path)]) == EXIT_OK

    committed = judged[-1]
    elaborated = elaborate(load_system(Path(source)), project_id="PRJ-LOCAL").snapshot
    assert set(elaborated.entities) <= set(committed.entities)
    verification = verification_of(committed)
    assert verification.result == "PASS" and verification.evidence[0] in committed.entities


def test_a_relaxed_constraint_re_enters_a_recorded_failure(tmp_path, ngspice, capsys):
    """A FAIL left the corner unknown; with the constraint relaxed and the
    program built again, verify does not print the old FAIL as current
    forever, nor run again: the recorded measurement re-enters and the gate
    passes it."""
    source = program(tmp_path, upper="1.2")
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_FAILED
    assert main(["verify", source, "-C", str(tmp_path)]) == EXIT_FAILED
    assert "current: this run is already recorded" in capsys.readouterr().out
    runs = len(ngspice.runs)

    program(tmp_path, upper="2")
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    capsys.readouterr()
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "current" not in output
    assert "re-entered through the gate" in output
    assert output.splitlines()[-2].strip() == "PASS"
    assert len(ngspice.runs) == runs


def test_a_changed_circuit_is_answered_again_and_not_reported_current(tmp_path, ngspice, capsys):
    """The committed corner was measured on a 10 kOhm resistor. With 22 kOhm
    the question is the same and the circuit is not: the measurement is not
    carried, so the question runs again instead of reporting the old PASS."""
    source = program(tmp_path)
    assert main(["build", source, "-C", str(tmp_path)]) == EXIT_OK
    assert main(["verify", source, "-C", str(tmp_path), "--commit"]) == EXIT_OK
    capsys.readouterr()
    runs = len(ngspice.runs)

    # A different length as well as a different value: a program rewritten
    # within the second at the same size could be read from stale bytecode.
    path = Path(source)
    path.write_text(path.read_text().replace("10 * kOhm)", "22 * kOhm)  # retuned"))
    main(["verify", source, "-C", str(tmp_path)])
    output = capsys.readouterr().out
    assert "current" not in output
    assert "  circuit level, ngspice (ngspice-45.2)" in output
    assert len(ngspice.runs) == runs + 1
    assert "22k" in ngspice.runs[-1] or "22000" in ngspice.runs[-1]
