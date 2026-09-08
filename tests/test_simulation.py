"""Spec: Simulation Is A Compiler Target; Simulation Plan Validation; SPICE
Lowering; The Backend Boundary; Normalized Simulation Results."""

from pathlib import Path

import pytest

from fang.elaborate import elaborate
from fang.lang import Parameter, Part, Power, System, V, kOhm, uF
from fang.parts import Capacitor, Resistor
from fang.simulation import (
    ACSweep,
    Assertion,
    BackendUnavailable,
    DCSweep,
    DETERMINISTIC_OPTIONS,
    Level,
    NgspiceBackend,
    NormalizedResult,
    OperatingPoint,
    RawResult,
    SimulationError,
    Transient,
    compile_plan,
    lower_to_spice,
    normalize,
    select_level,
)
from fang.traits import Simulatable

PROJECT = "PRJ-SIM"
RESISTOR_MODEL = dict(
    model_kind="resistor", backends=("ngspice",), pin_map={"1": "n1", "2": "n2"}
)


class Divider(System):
    top = Resistor(resistance=10 * kOhm)
    bottom = Resistor(resistance=4.7 * kOhm)

    def architecture(self):
        self.top.p2 >> self.bottom.p1


class Amplifier(Part):
    """A non-primitive part: SPICE has no built-in device for it."""

    designator_prefix = "U"
    supply = Power()
    gain = Parameter("1")


@pytest.fixture
def divider():
    result = elaborate(Divider, project_id=PROJECT)
    assert result.ok
    return result


# -- plan validation -------------------------------------------------------


def test_a_plan_is_explicit_before_anything_runs(divider):
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    assert plan.snapshot == divider.snapshot.hash
    assert plan.backend == "ngspice"
    assert plan.scope


def test_simulator_options_are_deterministic_and_recorded(divider):
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    for option, value in DETERMINISTIC_OPTIONS.items():
        assert plan.options[option] == value


def test_a_primitive_needs_no_model(divider):
    """SPICE has a resistor; asking for a model for one would be busywork."""
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    assert plan.models == () or all(m.model_kind for m in plan.models)


def test_a_non_primitive_with_no_model_rejects_the_plan():
    class Board(System):
        amplifier = Amplifier()
        load = Resistor(resistance=10 * kOhm)

    result = elaborate(Board, project_id=PROJECT)
    with pytest.raises(SimulationError, match="no simulation model"):
        compile_plan(result.snapshot, traits=result.traits)


def test_a_model_incompatible_with_the_backend_rejects_the_plan():
    class Board(System):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.amplifier.add_trait(
                Simulatable(model_kind="verilog_a", backends=("xyce",))
            )

        amplifier = Amplifier()

    result = elaborate(Board, project_id=PROJECT)
    with pytest.raises(SimulationError):
        compile_plan(result.snapshot, backend="ngspice", traits=result.traits)


def test_an_explicitly_abstracted_component_is_permitted_and_recorded():
    class Board(System):
        amplifier = Amplifier()
        load = Resistor(resistance=10 * kOhm)

    result = elaborate(Board, project_id=PROJECT)
    amplifier = next(
        e
        for e in result.snapshot.entities.values()
        if e.kind == "component" and e.identity.display_name == "Amplifier"
    )
    plan = compile_plan(
        result.snapshot, traits=result.traits, abstracted=[amplifier.id]
    )
    assert amplifier.id in plan.abstracted
    assert any("abstracted" in assumption for assumption in plan.assumptions)


def test_the_plan_states_what_it_does_not_cover(divider):
    plan = compile_plan(
        divider.snapshot, analysis=OperatingPoint(), traits=divider.traits
    )
    gaps = plan.coverage_gaps
    assert any("dynamic behaviour" in gap for gap in gaps)
    assert any("no probes" in gap for gap in gaps)


def test_a_transient_plan_records_its_stop_and_step(divider):
    plan = compile_plan(
        divider.snapshot,
        analysis=Transient(stop="10ms", step="1us", probes=("V(1)",)),
        traits=divider.traits,
    )
    assert plan.analysis.directive() == ".tran 1us 10ms"
    assert plan.analysis.as_dict()["stop"] == "10ms"


# -- lowering --------------------------------------------------------------


def test_the_lowering_emits_a_netlist_the_simulator_reads(divider):
    plan = compile_plan(
        divider.snapshot, analysis=OperatingPoint(probes=("V(1)",)), traits=divider.traits
    )
    deck = lower_to_spice(divider.snapshot, plan, traits=divider.traits)

    assert deck.startswith("* ")
    assert "R1 " in deck and "R2 " in deck
    assert ".op" in deck
    assert ".print operating_point V(1)" in deck
    assert deck.rstrip().endswith(".end")


def test_lowering_is_deterministic(divider):
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    first = lower_to_spice(divider.snapshot, plan, traits=divider.traits)
    second = lower_to_spice(divider.snapshot, plan, traits=divider.traits)
    assert first == second


def test_every_terminal_gets_a_node_even_when_it_is_floating(divider):
    """A dangling terminal is a fact about the circuit, not something to drop."""
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    deck = lower_to_spice(divider.snapshot, plan, traits=divider.traits)
    for line in deck.splitlines():
        if line.startswith("R"):
            parts = line.split()
            assert len(parts) >= 4, line          # name, node, node, value
            assert parts[1] != parts[2]


def test_an_abstracted_component_emits_no_device():
    class Board(System):
        amplifier = Amplifier()
        load = Resistor(resistance=10 * kOhm)

    result = elaborate(Board, project_id=PROJECT)
    amplifier = next(
        e
        for e in result.snapshot.entities.values()
        if e.kind == "component" and e.identity.display_name == "Amplifier"
    )
    plan = compile_plan(result.snapshot, traits=result.traits, abstracted=[amplifier.id])
    deck = lower_to_spice(result.snapshot, plan, traits=result.traits)
    assert "abstracted; no device emitted" in deck


def test_a_restricted_model_is_referenced_never_inlined():
    class Board(System):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.amplifier.add_trait(
                Simulatable(
                    model_kind="spice_subckt",
                    backends=("ngspice",),
                    source="vendor/SECRET.lib",
                    distribution_restricted=True,
                )
            )

        amplifier = Amplifier()

    result = elaborate(Board, project_id=PROJECT)
    plan = compile_plan(result.snapshot, traits=result.traits)
    deck = lower_to_spice(result.snapshot, plan, traits=result.traits)
    assert ".include vendor/SECRET.lib" in deck
    assert "SECRET" in deck and "subckt" not in deck.lower().replace("spice_subckt", "")


def test_the_deck_names_the_snapshot_it_came_from(divider):
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    deck = lower_to_spice(divider.snapshot, plan, traits=divider.traits)
    assert divider.snapshot.hash in deck


# -- the backend boundary --------------------------------------------------


def test_an_absent_simulator_reports_unsupported(tmp_path):
    backend = NgspiceBackend(executable="definitely-not-a-simulator")
    assert not backend.available()
    with pytest.raises(BackendUnavailable, match="not installed"):
        backend.run("* deck", workspace=tmp_path)
    with pytest.raises(BackendUnavailable):
        backend.version()


def test_the_backend_names_the_executable_it_looked_for(tmp_path):
    backend = NgspiceBackend(executable="not-a-simulator")
    with pytest.raises(BackendUnavailable, match="not-a-simulator"):
        backend.run("* deck", workspace=tmp_path)


@pytest.mark.skipif(
    not NgspiceBackend().available(), reason="ngspice is not installed here"
)
def test_an_invocation_is_recorded(divider, tmp_path):
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    deck = lower_to_spice(divider.snapshot, plan, traits=divider.traits)
    raw = NgspiceBackend().run(deck, workspace=tmp_path)
    assert raw.version
    assert raw.exit_status is not None
    assert raw.netlist == deck


# -- normalization ---------------------------------------------------------


def test_a_result_names_its_full_context(divider):
    plan = compile_plan(
        divider.snapshot, analysis=Transient(stop="1ms", step="1us", probes=("V(1)",)),
        traits=divider.traits,
    )
    raw = RawResult("ngspice", "ngspice-42", "", 0, "* deck")
    result = normalize(plan, raw, assertions=(Assertion("max(V(1)) < 3.5", "pass"),))
    rendered = result.as_dict()

    assert rendered["backend"] == "ngspice"
    assert rendered["backend_version"] == "ngspice-42"
    assert rendered["plan"]["analysis"]["kind"] == "transient"
    assert "models" in rendered and "assumptions" in rendered
    # A well-specified transient run has no gaps of its own; the bound on what
    # any simulation proves lives on the finding, where a consumer reads it.
    assert rendered["coverage_gaps"] == []
    assert "not proof of physical correctness" in rendered["finding"]["caveat"]


def test_sample_data_is_referenced_rather_than_inlined(divider):
    plan = compile_plan(
        divider.snapshot, analysis=OperatingPoint(probes=("V(1)", "I(V1)")),
        traits=divider.traits,
    )
    result = normalize(plan, RawResult("ngspice", "v", "", 0, ""))
    assert set(result.signals) == {"V(1)", "I(V1)"}
    for reference in result.signals.values():
        assert reference.startswith("artifact://")


def test_a_pass_is_a_finding_not_a_proof(divider):
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    result = normalize(
        plan, RawResult("ngspice", "v", "", 0, ""),
        assertions=(Assertion("max(V(1)) < 3.5", "pass"),),
    )
    assert result.passed
    finding = result.as_finding()
    assert finding["result"] == "PASS"
    assert finding["confidence"] == "inferred"
    assert "not proof of physical correctness" in finding["caveat"]
    assert finding["coverage_gaps"]


def test_an_undecided_assertion_does_not_pass(divider):
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    result = normalize(
        plan, RawResult("ngspice", "v", "", 0, ""),
        assertions=(Assertion("max(V(3v3))", "undecided"),),
    )
    assert not result.passed
    assert result.as_finding()["result"] == "FAIL"


def test_a_non_zero_exit_does_not_pass(divider):
    plan = compile_plan(divider.snapshot, traits=divider.traits)
    result = normalize(plan, RawResult("ngspice", "v", "", 1, ""))
    assert not result.passed


# -- verification levels ---------------------------------------------------


def test_the_cheapest_level_that_can_decide_is_selected():
    assert select_level(decidable_by_equation=True) is Level.EQUATION
    assert select_level(linear=True) is Level.SYMBOLIC
    assert select_level(system_level=True) is Level.BEHAVIOURAL
    assert select_level(needs_analog_detail=True) is Level.CIRCUIT
    assert select_level(needs_field_solver=True) is Level.EXTERNAL


def test_a_field_solver_question_beats_every_cheaper_level():
    assert select_level(decidable_by_equation=True, needs_field_solver=True) is Level.EXTERNAL
