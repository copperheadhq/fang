"""Spec: A Touchstone Model Is Data; Verification Tools Sit Behind One Protocol."""

from __future__ import annotations

import cmath
import math
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import FIXED_TIME

from fang import diagnostics
from fang.checks import DEFAULT_CHECKS
from fang.diagnostics import FangError
from fang.elaborate import elaborate
from fang.graph import KernelGraph
from fang.interfaces import AnalogIn, AnalogOut, Pin, PinMap
from fang.lang import GHz, Parameter, Part, System, dB, nH, pF, require
from fang.parts import Capacitor, Inductor
from fang.provenance import Provenance
from fang.rationale import Requires
from fang.rf import (
    TOUCHSTONE,
    TouchstoneError,
    quantize,
    read_touchstone,
)
from fang.simulation import Level
from fang.traits import Simulatable, Touchstone, TraitRegistry
from fang.units import Quantity
from fang.verification import (
    ANSWERED,
    FAILED,
    NOT_RUNNABLE,
    Evaluates,
    NotRunnable,
    ReturnLoss,
    answer,
    assumed_provenance,
    questions,
    route,
)

PROJECT = "PRJ-RF"
F = 2.44e9
OMEGA = 2 * math.pi * F


def s11(load: complex, reference: float) -> complex:
    return (load - reference) / (load + reference)


def write_model(path: Path, load: complex, *, unit="GHZ", form="MA", reference=50.0) -> Path:
    """A one-port file holding one load at three frequencies around 2.44 GHz,
    in the units, format and reference asked for."""
    scale = {"HZ": 1, "KHZ": 1e3, "MHZ": 1e6, "GHZ": 1e9}[unit]
    lines = ["! a test network, not a measurement", f"# {unit} S {form} R {reference:g}"]
    for frequency in (2.40e9, 2.44e9, 2.48e9):
        s = s11(load, reference)
        if form == "RI":
            pair = f"{s.real:.12g} {s.imag:.12g}"
        elif form == "MA":
            pair = f"{abs(s):.12g} {math.degrees(cmath.phase(s)):.12g}"
        else:
            pair = f"{20 * math.log10(abs(s)):.12g} {math.degrees(cmath.phase(s)):.12g}"
        lines.append(f"{frequency / scale:.12g} {pair}")
    path.write_text("\n".join(lines) + "\n")
    return path


class Antenna(Part):
    designator_prefix = "AE"
    rf = AnalogIn()
    FEED = Pin("FEED", role="analog", number="1")
    GND = Pin("GND", role="ground", number="2")
    pinmap = PinMap({"rf.signal": "FEED", "rf.ref": "GND"})


class Feed(Part):
    designator_prefix = "J"
    rf = AnalogOut()
    SIG = Pin("SIG", role="analog", number="1")
    GND = Pin("GND", role="ground", number="2")
    pinmap = PinMap({"rf.signal": "SIG", "rf.ref": "GND"})


def matched(model: Path, *, inductance=2 * nH, capacitance=1.5 * pF, at=2.44 * GHz,
            through=("shunt_c", "series_l"), provenance=None):
    """A feed, a shunt capacitor, a series inductor and an antenna."""

    class Matched(System):
        match_spec = Requires("At least 10 dB of return loss at 2.44 GHz")
        return_loss = Parameter("dB")

        feed = Feed()
        shunt_c = Capacitor(capacitance=capacitance) if capacitance else Capacitor()
        series_l = Inductor(inductance=inductance) if inductance else Inductor()
        antenna = Antenna()

        rl = Evaluates(
            "match_spec",
            measures={"return_loss": ReturnLoss("antenna.rf", at=at, through=through)},
        )

        def __init__(self, **overrides):
            super().__init__(**overrides)
            self.antenna.add_trait(
                Touchstone(
                    source=str(model),
                    ports=("FEED",),
                    provenance=provenance if provenance is not None else Provenance(),
                )
            )

        def architecture(self):
            self.feed.rf.signal >> self.shunt_c.p1
            self.feed.rf.signal >> self.series_l.p1
            self.shunt_c.p2 >> self.feed.rf.ref
            self.series_l.p2 >> self.antenna.rf.signal
            self.antenna.rf.ref >> self.feed.rf.ref

        def constraints(self):
            require(self.return_loss >= 10 * dB)

    return Matched


def evaluate(tmp_path, system):
    result = elaborate(system, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    outcome = answer(
        graph, questions(graph.head)[0], traits=result.traits, workspace=tmp_path,
        record_time=FIXED_TIME,
    )
    return graph, outcome


LOAD = complex(25, -10)


# -- the trait and the declaration -----------------------------------------------


def test_the_touchstone_trait_registers_and_enumerates_like_a_simulation_model():
    registry = TraitRegistry()
    registry.attach("CMP-antenna", Touchstone(source="chip.s1p", ports=("FEED",)))
    registry.attach("CMP-buffer", Simulatable(source="buffer.sub"))
    assert registry.entities_with("touchstone") == ["CMP-antenna"]
    assert registry.protocols() == ["simulatable", "touchstone"]
    record = registry.get("CMP-antenna", "touchstone").as_dict()
    assert record["protocol"] == "touchstone"
    assert (record["source"], record["ports"]) == ("chip.s1p", ["FEED"])


def test_an_rf_question_cannot_state_its_own_answer():
    with pytest.raises(FangError) as raised:
        Evaluates(
            "match_spec",
            measures={"return_loss": ReturnLoss("antenna.rf", at=2.44 * GHz)},
            result="PASS",
        )
    assert raised.value.diagnostic.code == diagnostics.SIM_QUESTION_RESULT


def test_a_return_loss_is_taken_at_a_frequency_against_a_resistance():
    with pytest.raises(FangError):
        ReturnLoss("antenna.rf", at=2 * nH)
    with pytest.raises(FangError):
        ReturnLoss("antenna.rf", at=2.44 * GHz, reference=50 * dB)


def test_a_return_loss_goes_only_into_a_parameter_declared_in_decibels(tmp_path):
    """A return loss is in dB, and a percent is as dimensionless as a dB:
    measured into a percent parameter, 10 dB would have been 1000 percent.
    The elaboration refuses it, as it refuses a measure of the wrong
    dimension."""
    model = write_model(tmp_path / "antenna.s1p", LOAD)

    class Linear(matched(model)):
        return_loss = Parameter("percent")

        def constraints(self):
            pass

    result = elaborate(Linear, project_id=PROJECT)
    assert not result.ok
    assert result.diagnostics[0].code == diagnostics.UNIT_DIMENSION_MISMATCH
    assert "decibels" in result.diagnostics[0].message


def test_an_rf_question_routes_to_the_equation_level(tmp_path):
    model = write_model(tmp_path / "antenna.s1p", LOAD)
    snapshot = elaborate(matched(model), project_id=PROJECT).snapshot
    routed = route(snapshot, questions(snapshot)[0])
    assert (routed.level, routed.tool) == (Level.EQUATION, "touchstone")
    assert not routed.decided


# -- reading the file ------------------------------------------------------------


def test_the_files_format_options_are_honoured():
    """One network in three units, three formats and two references reads
    back as the same load."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as scratch:
        loads = []
        for unit, form, reference in (("GHZ", "MA", 50.0), ("MHZ", "RI", 75.0), ("KHZ", "DB", 50.0)):
            path = write_model(Path(scratch) / f"{form}.s1p", LOAD, unit=unit, form=form, reference=reference)
            network = read_touchstone(path.read_text(), ports=1)
            loads.append(network.impedance(network.reflection(F)))
    for load in loads:
        assert abs(load - LOAD) < 1e-6


def test_two_files_in_different_formats_give_the_same_measurement(tmp_path):
    first = write_model(tmp_path / "ma.s1p", LOAD, unit="GHZ", form="MA", reference=50.0)
    second = write_model(tmp_path / "ri.s1p", LOAD, unit="MHZ", form="RI", reference=75.0)
    _, one = evaluate(tmp_path / "one", matched(first))
    _, two = evaluate(tmp_path / "two", matched(second))
    assert one.measurements[0].quantity == two.measurements[0].quantity
    assert one.measurements[0].quantity is not None


def test_a_file_of_other_parameters_is_refused():
    with pytest.raises(TouchstoneError, match="only S"):
        read_touchstone("# GHZ Z RI R 50\n2.4 50 0\n", ports=1)
    with pytest.raises(TouchstoneError, match="do not ascend"):
        read_touchstone("# GHZ S RI R 50\n2.4 0 0\n2.3 0 0\n", ports=1)


# -- composing the match ---------------------------------------------------------


def test_a_one_port_file_answers_a_return_loss_question(tmp_path):
    """100 Ohm against 50 Ohm reflects a third: 20 log10 3 = 9.54243 dB."""
    model = write_model(tmp_path / "antenna.s1p", complex(100, 0))
    graph, outcome = evaluate(tmp_path, matched(model, through=()))
    assert outcome.measurements[0].quantity == Quantity.scalar("9.54243", "dB")
    # 9.54 dB is short of the 10 dB required: recorded as a failure, not applied.
    assert (outcome.status, outcome.result) == (FAILED, "FAIL")
    record = graph.head.entities[outcome.evidence].extensions["measurement"]
    assert record["measures"][0]["value"] == "9.54243"


def test_a_matching_network_is_composed_from_the_graphs_values(tmp_path):
    """Worked by hand: the inductor in series with the load, then the
    capacitor across the port."""
    model = write_model(tmp_path / "antenna.s1p", LOAD)
    graph, outcome = evaluate(tmp_path, matched(model))

    inductance, capacitance = 2e-9, 1.5e-12
    after_inductor = LOAD + 1j * OMEGA * inductance
    seen = 1 / (1 / after_inductor + 1j * OMEGA * capacitance)
    gamma = abs((seen - 50) / (seen + 50))
    expected = Decimal(format(-20 * math.log10(gamma), ".6g"))

    measured = outcome.measurements[0].quantity
    assert measured == Quantity.scalar(expected, "dB")
    # Without the network the same antenna reads differently: both parts count.
    _, bare = evaluate(tmp_path / "bare", matched(model, through=()))
    assert bare.measurements[0].quantity != measured
    assert outcome.result == "PASS"


def test_a_matching_part_with_an_unknown_value_leaves_the_question_unanswered(tmp_path):
    model = write_model(tmp_path / "antenna.s1p", LOAD)
    graph, outcome = evaluate(tmp_path, matched(model, inductance=None))
    (measurement,) = outcome.measurements
    assert measurement.quantity is None
    assert "system.series_l's inductance is unknown" in measurement.reason
    assert outcome.result == "UNKNOWN"
    assert not graph.head.entities[measurement.entity].parameters["return_loss"].known


def test_a_frequency_outside_the_file_is_refused_naming_the_range(tmp_path):
    model = write_model(tmp_path / "antenna.s1p", LOAD)
    result = elaborate(matched(model, at=3 * GHz), project_id=PROJECT)
    with pytest.raises(NotRunnable) as raised:
        TOUCHSTONE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits)
    assert raised.value.code == diagnostics.SIM_OUTSIDE_MODEL_RANGE
    assert "2.4 GHz to 2.48 GHz" in str(raised.value)
    assert "nothing is extrapolated" in str(raised.value)

    graph, outcome = evaluate(tmp_path, matched(model, at=3 * GHz))
    assert outcome.status == NOT_RUNNABLE and outcome.result == "UNKNOWN"


def test_a_question_at_the_files_last_point_is_inside_its_range(tmp_path):
    """2.01 GHz scaled to hertz in binary floats is 2009999999.9999998, just
    below the 2.01 GHz a question names, which was then refused as outside
    the file. Frequencies are scaled and compared as decimals."""
    network = read_touchstone("# GHZ S RI R 50\n2.00 0 0\n2.01 0.5 0\n", ports=1)
    assert network.span == (Decimal("2.00E9"), Decimal("2.01E9"))
    assert network.reflection(Decimal("2010000000")) == complex(0.5, 0)

    model = tmp_path / "antenna.s1p"
    model.write_text("# GHZ S RI R 50\n1.99 0 0\n2.00 0 0\n2.01 0.333333333333 0\n")
    result = elaborate(matched(model, at=2.01 * GHz, through=()), project_id=PROJECT)
    job = TOUCHSTONE.prepare(result.snapshot, questions(result.snapshot)[0], traits=result.traits)
    assert '"at":"2010000000"' in job.input

    graph, outcome = evaluate(tmp_path, matched(model, at=2.01 * GHz, through=()))
    assert outcome.status != NOT_RUNNABLE
    assert outcome.measurements[0].quantity == Quantity.scalar("9.54243", "dB")


def test_confidence_is_bounded_by_the_models_provenance(tmp_path):
    model = write_model(tmp_path / "antenna.s1p", LOAD)
    _, assumed = evaluate(tmp_path / "a", matched(model, provenance=assumed_provenance("synthetic")))
    assert assumed.measurements[0].confidence == Decimal("0.5")
    record = assumed.job.inputs
    assert list(record) == ["models/antenna.s1p"]


# -- the decimal boundary -----------------------------------------------------------


def test_results_cross_into_decimal_at_six_significant_figures(tmp_path):
    assert quantize(9.542425094393248) == Decimal("9.54243")
    assert quantize(math.inf) == Decimal("Infinity")
    model = write_model(tmp_path / "antenna.s1p", LOAD)
    _, first = evaluate(tmp_path / "1", matched(model))
    _, second = evaluate(tmp_path / "2", matched(model))
    text = first.measurements[0].quantity.as_dict()["value"]
    assert text == second.measurements[0].quantity.as_dict()["value"]
    assert len(text.replace(".", "").lstrip("0")) <= 6


def test_preparation_is_deterministic_and_records_the_model_digest(tmp_path):
    model = write_model(tmp_path / "antenna.s1p", LOAD)
    result = elaborate(matched(model), project_id=PROJECT)
    question = questions(result.snapshot)[0]
    first = TOUCHSTONE.prepare(result.snapshot, question, traits=result.traits)
    again = TOUCHSTONE.prepare(result.snapshot, question, traits=result.traits)
    assert first.input == again.input and first.hash == again.hash
    assert '"kind":"shunt"' in first.input and '"kind":"series"' in first.input


def test_two_antennas_naming_one_model_path_each_read_their_own_file(tmp_path):
    """Two antennas declared in different folders name their files by one
    relative path, and the files differ. Named by the path alone they shared
    one bundle entry, so both measures read one file; each is now named
    under its own digest."""
    import importlib.util

    def declared_in(folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        stage = folder / "stage.py"
        stage.write_text("def instance(part):\n    return part()\n")
        spec = importlib.util.spec_from_file_location(f"stage_{folder.name}", stage)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.instance(Antenna)

    class Pair(System):
        match_spec = Requires("At least 6 dB of return loss at 2.44 GHz at either antenna")
        near_loss = Parameter("dB")
        far_loss = Parameter("dB")

        near_feed = Feed()
        far_feed = Feed()
        near = declared_in(tmp_path / "a")
        far = declared_in(tmp_path / "b")

        rl = Evaluates(
            "match_spec",
            measures={
                "near_loss": ReturnLoss("near.rf", at=2.44 * GHz),
                "far_loss": ReturnLoss("far.rf", at=2.44 * GHz),
            },
        )

        def __init__(self, **overrides):
            super().__init__(**overrides)
            for antenna in (self.near, self.far):
                antenna.add_trait(Touchstone(source="antenna.s1p", ports=("FEED",)))

        def architecture(self):
            for feed, antenna in ((self.near_feed, self.near), (self.far_feed, self.far)):
                feed.rf.signal >> antenna.rf.signal
                feed.rf.ref >> antenna.rf.ref

    write_model(tmp_path / "a" / "antenna.s1p", complex(100, 0))   # a third: 9.54243 dB
    write_model(tmp_path / "b" / "antenna.s1p", complex(150, 0))   # a half: 6.0206 dB
    graph, outcome = evaluate(tmp_path / "runs", Pair)
    measured = {m.name: m.quantity for m in outcome.measurements}
    assert measured == {
        "near_loss": Quantity.scalar("9.54243", "dB"),
        "far_loss": Quantity.scalar("6.0206", "dB"),
    }
    assert len(outcome.job.inputs) == 2
    assert all(path.endswith("/antenna.s1p") and len(path) == 12 + len("/antenna.s1p")
               for path in outcome.job.inputs)
