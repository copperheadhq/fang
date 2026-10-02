"""Spec: "The Emulator Script Carries Only What The Lowering Writes",
"Observation Comes From Probes, Not From The Firmware's Report", "Pin
Configuration Is Measured", "Absence Is An Observation; An Incomplete Run Is
Not", "Emulation Runs Are Deterministic And Identified", and "The Emulator Is
Reported, Never Substituted".

The lowering and the measures are pure, so most of this runs without Renode:
the measures read event records recorded from the sensor_node firmware by
Renode 1.17.0 and committed under tests/fixtures/renode/events/. The tests
that run Renode skip by name where it is not installed.
"""

import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from fang.emulation import (
    INFINITY,
    EmulationPlan,
    Event,
    PlanBus,
    PlanDevice,
    PlanObservation,
    PlanPin,
    PlanRegister,
    PlanStimulus,
    PlanWatch,
    RunRecord,
    coverage_gaps_observed,
    descriptor,
    descriptors,
    measure,
    read_events,
    register_values,
    run_record,
)
from fang.renode import LoweringError, RenodeBackend, bundle, platform_description, script, seconds
from fang.renode.lowering import FIRMWARE, MANIFEST, PLAN

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "renode" / "events"
ELF = ROOT / "examples" / "sensor_node" / "firmware" / "elf"

needs_renode = pytest.mark.skipif(
    shutil.which("renode") is None, reason="renode is not installed"
)


def plan(*, absent: bool = False, status_pin: int = 5, stimuli=None, run_until_ns=2_000_000_000):
    """The sensor_node startup plan, written by hand with readable entity ids:
    the ids the committed event fixtures were recorded with."""
    pins = (
        PlanPin("PIN-PB8", "PB8", "scl", "AF4", True, "gpioPortB", 8),
        PlanPin("PIN-PB9", "PB9", "sda", "AF4", True, "gpioPortB", 9),
    )
    device = PlanDevice(
        "env", "env", "renode:Sensors.HS3001", "Antmicro.Renode.Peripherals.Sensors.HS3001", 0x44, absent
    )
    if stimuli is None:
        stimuli = () if absent else (
            PlanStimulus(0, "env", "env", "temperature", "Temperature", "25", "degC"),
        )
    return EmulationPlan(
        question="VER-startup",
        requirement="REQ-sensor",
        snapshot="sha256:x",
        machine="sensor_node",
        platform="fang:stm32f401re",
        platform_file="platforms/stm32f401re.repl",
        recorder_port="gpioPortA",
        target="mcu",
        firmware_path="firmware/elf/sensor_node.elf",
        firmware_target="stm32f401re",
        core_clock_hz=16_000_000,
        seed=42,
        run_until_ns=run_until_ns,
        buses=(PlanBus("mcu.i2c1", "I2C1", "i2c1", pins, (device,)),),
        observations=(
            PlanObservation("status", "gpio", "mcu.status", "mcu.status", "gpioPortA", status_pin),
            PlanObservation("console", "uart", "mcu.usart2", "mcu.usart2", "usart2"),
        ),
        watched=(PlanWatch("i2c1Warnings", "i2c1", "mcu.i2c1"),),
        registers=(
            PlanRegister("mcu", "gpioPortB", "MODER", 0x40020400, 0x280, True),
            PlanRegister("mcu", "gpioPortB", "OTYPER", 0x40020404, 0, False),
            PlanRegister("mcu", "gpioPortB", "AFRH", 0x40020424, 0, True),
        ),
        stimuli=stimuli,
        measures={
            "first_read": {"kind": "first_at", "matches": [{"kind": "i2c.read", "entity": "env"}]},
            "slow_blinks": {
                "kind": "count",
                "matches": [{"kind": "gpio.rise", "entity": "mcu.status"}],
                "within_ns": [1_000_000_000, 2_000_000_000],
            },
            "reported": {"kind": "uart_value", "entity": "mcu.usart2", "prefix": "temp=", "unit": "degC"},
            "mux_mismatches": {"kind": "pin_config", "entity": "mcu.i2c1"},
        },
        expected_warnings=tuple(
            {"model": "fang:stm32f401re", **w} for w in descriptor("fang:stm32f401re").expected_warnings
        ),
    )


def recorded(name: str) -> RunRecord:
    return run_record((FIXTURES / f"{name}.jsonl").read_bytes(), "completed")


def measured(p: EmulationPlan, record: RunRecord) -> dict:
    return {m.name: m for m in measure(p, record)}


# -- descriptors --------------------------------------------------------------


def test_the_shipped_descriptors_load():
    assert set(descriptors()) == {"fang:stm32f401re", "renode:Sensors.HS3001"}
    assert descriptor("renode:Sensors.HS3001").faults == ("absent",)


def test_an_unknown_model_is_refused_rather_than_substituted():
    with pytest.raises(ValueError, match="no emulation model descriptor"):
        descriptor("renode:Sensors.Generic")


def test_a_pin_maps_to_its_port_by_the_descriptor_not_by_its_name():
    pins = descriptor("fang:stm32f401re").document["pins"]
    assert pins["PA5"] == {"port": "gpioPortA", "index": 5}
    assert pins["PB9"] == {"port": "gpioPortB", "index": 9}


# -- the lowering -------------------------------------------------------------


@pytest.mark.parametrize(
    "nanoseconds, text",
    [(100_000_000, "0.1"), (2_000_000_000, "2"), (1_000_000, "0.001"), (1, "0.000000001"), (20_000_000_000, "20")],
)
def test_durations_are_decimal_seconds(nanoseconds, text):
    # Renode reads "100ms" as a hundred seconds; the lowering never writes a unit.
    assert seconds(nanoseconds) == text


def test_the_seed_comes_first_and_the_run_ends_explicitly():
    lines = script(plan()).splitlines()
    assert lines[0] == "emulation SetSeed 42"
    assert lines[-2:] == ['sysbus.gpioPortA.recorder Finish "completed"', "quit"]


def test_every_file_is_named_relative_to_the_script():
    text = script(plan())
    assert "$ORIGIN/platform.repl" in text and "$ORIGIN/firmware.elf" in text
    assert " @" not in text


def test_a_stimulus_is_applied_at_its_virtual_time():
    stimuli = (
        PlanStimulus(0, "env", "env", "temperature", "Temperature", "25", "degC"),
        PlanStimulus(100_000_000, "env", "env", "temperature", "Temperature", "30.5", "degC"),
    )
    lines = script(plan(stimuli=stimuli)).splitlines()
    first = lines.index('sysbus.i2c1.env SetInput "Temperature" "25"')
    assert lines[first + 1] == 'emulation RunFor "0.1"'
    assert lines[first + 2] == 'sysbus.i2c1.env SetInput "Temperature" "30.5"'
    assert lines[first + 3] == 'emulation RunFor "1.9"'


def test_an_absent_device_has_no_probe_and_no_stimulus():
    text = platform_description(plan(absent=True))
    assert "I2CProbe" not in text
    assert "SetInput" not in script(plan(absent=True))


def test_text_that_could_reach_the_monitor_is_refused():
    hostile = PlanObservation('st"atus', "gpio", "mcu.status", "mcu.status", "gpioPortA", 5)
    p = plan()
    with pytest.raises(LoweringError):
        platform_description(EmulationPlan(**{**p.__dict__, "observations": (hostile,)}))
    quoted = PlanObservation("status", "gpio", 'mcu"; quit', "mcu.status", "gpioPortA", 5)
    with pytest.raises(LoweringError):
        platform_description(EmulationPlan(**{**p.__dict__, "observations": (quoted,)}))


def test_lowering_is_deterministic_and_the_manifest_names_every_digest():
    firmware = (ELF / "sensor_node.elf").read_bytes()
    first, second = bundle(plan(), firmware), bundle(plan(), firmware)
    assert first == second
    assert first[FIRMWARE] == firmware
    manifest = first[MANIFEST].decode()
    assert plan().hash in manifest
    for name in (PLAN, "platform.repl", "run.resc", "fang_probes.cs", "stm32f401re.repl"):
        assert f'"{name}"' in manifest


def test_the_plan_hash_does_not_cover_the_snapshot_hash():
    p = plan()
    moved = EmulationPlan(**{**p.__dict__, "snapshot": "sha256:elsewhere"})
    assert moved.hash == p.hash
    # Nor does the bundle: the plan it carries names no snapshot.
    firmware = (ELF / "sensor_node.elf").read_bytes()
    assert moved.as_dict() == p.as_dict() and "snapshot" not in p.as_dict()
    assert bundle(moved, firmware) == bundle(p, firmware)


# -- events -------------------------------------------------------------------


def test_the_event_record_reads_in_order():
    events = read_events((FIXTURES / "startup.jsonl").read_bytes())
    assert events[0].type == "run.start"
    assert events[-1].type == "run.end"
    assert [e.seq for e in events] == list(range(len(events)))


def test_an_out_of_order_record_is_refused():
    data = b'{"seq":0,"t_ns":5,"source":"","type":"a","payload":{}}\n{"seq":1,"t_ns":4,"source":"","type":"b","payload":{}}\n'
    with pytest.raises(ValueError, match="out of order"):
        read_events(data)


def test_a_cut_off_last_line_is_dropped():
    data = b'{"seq":0,"t_ns":5,"source":"","type":"a","payload":{}}\n{"seq":1,"t_ns'
    assert len(read_events(data)) == 1


# -- measures over recorded runs ----------------------------------------------


def test_the_startup_run_measures_what_the_firmware_did():
    m = measured(plan(), recorded("startup"))
    assert m["first_read"].quantity.value == Decimal("0.03999834")
    assert m["slow_blinks"].quantity.value == 1
    assert m["reported"].quantity.value == Decimal("25.01")
    assert m["mux_mismatches"].quantity.value == 0


def test_a_printed_value_is_marked_as_the_firmwares_report():
    m = measured(plan(), recorded("startup"))
    assert m["reported"].firmware_report
    assert not m["first_read"].firmware_report


def test_a_read_that_never_happens_is_measured_after_the_runs_end():
    m = measured(plan(), recorded("wrong_address"))
    first_read = m["first_read"].quantity
    assert first_read.interval() == (Decimal(2), INFINITY)
    # Against `first_read <= 200 ms` the whole interval lies above the bound.
    assert first_read.interval()[0] > Decimal("0.2")


def test_a_short_run_cannot_fail_a_later_bound():
    events = (
        Event(0, 0, "", "run.start", {}),
        Event(1, 100_000_000, "", "run.end", {"reason": "completed"}),
    )
    m = measured(plan(run_until_ns=100_000_000), RunRecord(events, "completed"))
    low, high = m["first_read"].quantity.interval()
    # [0.1 s, infinity) straddles 0.2 s: the comparison stays undecided.
    assert low < Decimal("0.2") < high


def test_a_timed_out_run_decides_nothing():
    record = RunRecord(recorded("startup").events[:40], "timeout")
    for value in measure(plan(), record):
        assert value.quantity is None
        assert "timeout" in value.reason


def test_an_unexpected_model_warning_withdraws_the_measures_over_it():
    events = list(recorded("startup").events)
    warning = Event(events[3].seq, events[3].t_ns, "env", "model.warning", {"text": "Unexpected write to the sensor"})
    renumbered = [*events[:3], warning, *(Event(e.seq + 1, e.t_ns, e.source, e.type, e.payload) for e in events[3:])]
    m = measured(plan(), RunRecord(tuple(renumbered), "completed"))
    assert m["first_read"].quantity is None
    assert "Unexpected write to the sensor" in m["first_read"].reason
    assert m["slow_blinks"].quantity is not None


def test_expected_warnings_are_coverage_gaps_not_withdrawals():
    record = recorded("startup")
    assert "I2C bus timing (CCR, TRISE)" in coverage_gaps_observed(record, plan())
    assert measured(plan(), record)["first_read"].quantity is not None


def _warned(source: str, text: str) -> RunRecord:
    """The startup run with one more model warning, recorded under `source`."""
    events = list(recorded("startup").events)
    warning = Event(events[3].seq, events[3].t_ns, source, "model.warning", {"text": text})
    later = (Event(e.seq + 1, e.t_ns, e.source, e.type, e.payload) for e in events[3:])
    return RunRecord((*events[:3], warning, *later), "completed")


def test_a_warning_the_platform_expects_still_withdraws_the_sensors_measures():
    # The patterns were pooled across descriptors, so a sensor warning that
    # matched the platform's timing-register pattern was taken as expected.
    text = "Unhandled write to offset 0x1C. Unhandled bits: [4, 6] when writing value 0x50."
    m = measured(plan(), _warned("env", text))
    assert m["first_read"].quantity is None
    assert "withdrawn: env" in m["first_read"].reason and "0x1C" in m["first_read"].reason
    assert m["slow_blinks"].quantity is not None


def test_a_warning_the_sensor_expects_is_expected_only_of_the_sensor():
    p = plan()
    quirk = {"model": "renode:Sensors.HS3001", "gap": "the sensor's quirk", "pattern": "Sensor quirk"}
    quirky = EmulationPlan(**{**p.__dict__, "expected_warnings": (*p.expected_warnings, quirk)})

    from_sensor = _warned("env", "Sensor quirk at 0x44")
    assert measured(quirky, from_sensor)["first_read"].quantity is not None
    assert "the sensor's quirk" in coverage_gaps_observed(from_sensor, quirky)

    from_bus = _warned("mcu.i2c1", "Sensor quirk at 0x44")
    assert measured(quirky, from_bus)["first_read"].quantity is None
    assert "the sensor's quirk" not in coverage_gaps_observed(from_bus, quirky)


def test_each_expected_warning_in_a_plan_names_its_descriptor():
    from fang.emulation import compile_plan

    result, paths = _board()
    compiled = compile_plan(result.snapshot, _Question(_startup_data(paths)), traits=result.traits)
    assert {w["model"] for w in compiled.expected_warnings} == {"fang:stm32f401re"}
    assert [dict(w) for w in compiled.expected_warnings] == [dict(w) for w in plan().expected_warnings]


def test_a_push_pull_build_is_caught_though_every_transaction_succeeded():
    m = measured(plan(), recorded("push_pull"))
    assert m["mux_mismatches"].quantity.value == 2
    assert m["first_read"].quantity.value < Decimal("0.2")


def test_an_unstored_register_is_judged_by_its_writes():
    values = register_values(plan(), recorded("startup"))
    assert values[("gpioPortB", "OTYPER")] == 0x300


def test_the_led_on_another_pin_never_rises():
    assert measured(plan(status_pin=6), recorded("led_on_pa6"))["slow_blinks"].quantity.value == 0


def test_a_missing_sensor_leaves_the_firmware_blinking_fast():
    m = measured(plan(absent=True), recorded("absent"))
    assert m["slow_blinks"].quantity.value >= 4
    assert m["first_read"].quantity.interval()[1] == INFINITY


def test_a_firmware_with_no_timeout_hangs_on_a_missing_sensor():
    m = measured(plan(absent=True), recorded("no_timeout_absent"))
    assert m["slow_blinks"].quantity.value == 0


def test_a_window_past_the_runs_end_is_a_lower_bound():
    p = plan()
    late = EmulationPlan(**{**p.__dict__, "measures": {
        "late": {"kind": "count", "matches": [{"kind": "gpio.rise", "entity": "mcu.status"}],
                 "within_ns": [1_000_000_000, 3_000_000_000]},
    }})
    count = measured(late, recorded("startup"))["late"].quantity
    assert count.interval() == (Decimal(1), INFINITY)


# -- Renode itself ------------------------------------------------------------


def test_a_missing_emulator_reports_unsupported(monkeypatch):
    backend = RenodeBackend(executable="renode-that-is-not-installed")
    assert not backend.available()
    with pytest.raises(Exception, match="not installed"):
        backend.run({}, timeout=5)


@needs_renode
def test_a_live_run_reproduces_the_recorded_events():
    run = RenodeBackend().run(bundle(plan(), (ELF / "sensor_node.elf").read_bytes()), timeout=180)
    assert run.version == "1.17.0"
    assert run.outcome == "completed"
    assert run.events == (FIXTURES / "startup.jsonl").read_bytes()


# -- compiling a plan from the sensor_node board ------------------------------


def _board():
    """sensor_node elaborated, with its emulation traits attached by hand."""
    from fang.cli import load_system
    from fang.elaborate import elaborate
    from fang.emulation import EmulationModel, Firmware

    result = elaborate(load_system(ROOT / "examples" / "sensor_node" / "sensor_node.py"), project_id="PRJ-EXAMPLES")
    paths = {str(e.identity.path): e.id for e in result.snapshot.entities.values() if e.identity.path is not None}
    result.traits.attach(paths["system.mcu"], EmulationModel(source="fang:stm32f401re"))
    result.traits.attach(paths["system.mcu"], Firmware("firmware/elf/sensor_node.elf", target="stm32f401re"))
    result.traits.attach(paths["system.env"], EmulationModel(source="renode:Sensors.HS3001"))
    return result, paths


class _Question:
    def __init__(self, data):
        self.id, self.verifies, self.data = "VER-startup", "REQ-sensor", data


def _scalar(value, unit):
    return {"kind": "scalar", "unit": unit, "value": value}


def _startup_data(paths, *, abstracted=("scl_pullup", "sda_pullup", "series", "console"), faults=(), stimuli=None):
    if stimuli is None:
        stimuli = [{"at": _scalar("0", "ms"), "surface": "env", "input": "temperature", "quantity": _scalar("25", "degC")}]
    return {
        "method": "emulation",
        "surfaces": {
            "env": {"kind": "part", "component": paths["system.env"]},
            "mcu.status": {"kind": "surface", "component": paths["system.mcu"], "port": paths["system.mcu.status"]},
            "mcu.usart2": {"kind": "surface", "component": paths["system.mcu"], "port": paths["system.mcu.usart2"]},
            "mcu.i2c1": {"kind": "surface", "component": paths["system.mcu"], "port": paths["system.mcu.i2c1"]},
        },
        "abstracted": [{"name": n, "component": paths[f"system.{n}"]} for n in abstracted],
        "measures": [
            {"name": "first_read", "parameter": "X.first_read", "unit": "s",
             "measure": {"kind": "emulation.first_at", "surface": "env", "match": {"kind": "i2c.read", "surface": "env"}}},
            {"name": "reported", "parameter": "X.reported", "unit": "degC",
             "measure": {"kind": "emulation.uart_value", "surface": "mcu.usart2", "prefix": "temp=", "unit": "degC"}},
            {"name": "slow_blinks", "parameter": "X.slow_blinks", "unit": "1",
             "measure": {"kind": "emulation.count", "surface": "mcu.status",
                         "match": {"kind": "gpio.rise", "surface": "mcu.status"}, "within_ns": [1_000_000_000, 2_000_000_000]}},
            {"name": "mux_mismatches", "parameter": "X.mux_mismatches", "unit": "1",
             "measure": {"kind": "emulation.pin_config", "surface": "mcu.i2c1"}},
        ],
        "scenario": {"run_until": _scalar("2", "s"), "seed": 0, "stimuli": stimuli, "faults": list(faults)},
    }


def test_the_plan_carries_the_boards_facts():
    from fang.emulation import compile_plan

    result, paths = _board()
    plan = compile_plan(result.snapshot, _Question(_startup_data(paths)), traits=result.traits)
    (bus,) = plan.buses
    assert (bus.instance, bus.emulator) == ("I2C1", "i2c1")
    assert [(p.vendor, p.signal, p.selector, p.open_drain) for p in bus.pins] == [
        ("PB8", "scl", "AF4", True), ("PB9", "sda", "AF4", True),
    ]
    assert [(d.address, d.model) for d in bus.devices] == [(0x44, "renode:Sensors.HS3001")]
    gpio = next(o for o in plan.observations if o.kind == "gpio")
    assert (gpio.emulator, gpio.index) == ("gpioPortA", 5)
    assert plan.stimuli[0].value == "25"
    assert "scl_pullup is abstracted, not modelled" in plan.coverage_gaps


def test_the_same_question_compiles_to_the_same_plan():
    from fang.emulation import compile_plan

    first, paths = _board()
    second, _ = _board()
    a = compile_plan(first.snapshot, _Question(_startup_data(paths)), traits=first.traits)
    b = compile_plan(second.snapshot, _Question(_startup_data(paths)), traits=second.traits)
    assert a.hash == b.hash and a.as_dict() == b.as_dict()


def test_a_component_in_scope_with_no_model_and_no_abstraction_refuses_the_plan():
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    with pytest.raises(EmulationError, match="scl_pullup"):
        compile_plan(result.snapshot, _Question(_startup_data(paths, abstracted=("sda_pullup", "series", "console"))),
                     traits=result.traits)


def test_an_unsupported_fault_refuses_the_plan():
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    data = _startup_data(paths, faults=[{"kind": "stuck_low", "surface": "env"}])
    with pytest.raises(EmulationError):
        compile_plan(result.snapshot, _Question(data), traits=result.traits)


def test_a_stimulus_of_the_wrong_dimension_refuses_the_plan():
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    stimuli = [{"at": _scalar("0", "ms"), "surface": "env", "input": "temperature", "quantity": _scalar("3", "V")}]
    with pytest.raises(EmulationError, match="temperature"):
        compile_plan(result.snapshot, _Question(_startup_data(paths, stimuli=stimuli)), traits=result.traits)


def test_a_plan_without_a_duration_is_refused():
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    data = _startup_data(paths)
    del data["scenario"]["run_until"]
    with pytest.raises(EmulationError, match="duration"):
        compile_plan(result.snapshot, _Question(data), traits=result.traits)


@pytest.mark.parametrize("duration", ["-1", "0"])
def test_a_run_of_no_time_or_less_is_refused_where_it_is_declared(duration):
    # A negative run_until passed the dimension check, and its lowering wrote
    # no RunFor and still finished "completed".
    from fang.diagnostics import FangError
    from fang.emulation import Emulates, FirstAt, I2CRead
    from fang.units import Quantity

    with pytest.raises(FangError) as refused:
        Emulates("sensor_ready", run_until=Quantity.scalar(Decimal(duration), "s"),
                 measures={"first_read": FirstAt(I2CRead("env"))})
    assert refused.value.diagnostic.code == "SIM-0014"
    assert refused.value.diagnostic.location.file == __file__


@pytest.mark.parametrize("duration", ["-1", "0"])
def test_a_plan_of_no_time_or_less_is_refused_as_a_duration(duration):
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    data = _startup_data(paths, stimuli=[])
    data["scenario"]["run_until"] = _scalar(duration, "s")
    with pytest.raises(EmulationError, match="positive time") as refused:
        compile_plan(result.snapshot, _Question(data), traits=result.traits)
    assert refused.value.code == "duration"


@pytest.mark.parametrize("nanoseconds", [-1_000_000_000, 0])
def test_a_plan_of_no_time_or_less_is_not_lowered(nanoseconds):
    # Lowered, it would finish "completed" having run nothing.
    with pytest.raises(LoweringError, match="no time"):
        script(plan(run_until_ns=nanoseconds, stimuli=()))


@needs_renode
def test_a_plan_compiled_from_the_board_runs_and_measures():
    from fang.emulation import compile_plan

    result, paths = _board()
    plan = compile_plan(result.snapshot, _Question(_startup_data(paths)), traits=result.traits)
    firmware = (ROOT / "examples" / "sensor_node" / plan.firmware_path).read_bytes()
    run = RenodeBackend().run(bundle(plan, firmware), timeout=180)
    m = measured(plan, run_record(run.events, run.outcome))
    assert m["first_read"].quantity.interval()[1] < Decimal("0.2")
    assert m["reported"].quantity.value == Decimal("25.01")
    assert m["slow_blinks"].quantity.value == 1
    assert m["mux_mismatches"].quantity.value == 0


# -- the lowering against the spike's hand-written files -----------------------


def test_the_lowering_reproduces_the_spikes_hand_written_files():
    """The spike wrote the platform description and the script by hand and ran
    them against Renode 1.17.0; the lowering reproduces both byte for byte."""
    golden = ROOT / "tests" / "fixtures" / "renode" / "golden"
    assert platform_description(plan()) == (golden / "platform.repl").read_text()
    assert script(plan()) == (golden / "run.resc").read_text()


# -- declaring, routing and answering an emulation question -------------------

import importlib.util
import subprocess

from fang.checks import DEFAULT_CHECKS
from fang.entities import Evidence, Verification
from fang.graph import KernelGraph
from fang.simulation import Level
from fang.verification import NotRunnable, answer, questions, route


def _sensor_node_module():
    spec = importlib.util.spec_from_file_location(
        "sensor_node_for_tests", ROOT / "examples" / "sensor_node" / "sensor_node.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SENSOR_NODE = _sensor_node_module()


def _elaborate(system):
    from fang.elaborate import elaborate

    result = elaborate(system, project_id="PRJ-EXAMPLES")
    assert result.ok, [d.message for d in result.diagnostics]
    return result


def _question(snapshot, attribute):
    return next(q for q in questions(snapshot) if q.label.endswith(f".{attribute}"))


def test_an_emulation_question_elaborates_to_an_unanswered_verification():
    result = _elaborate(SENSOR_NODE.SensorNode)
    question = _question(result.snapshot, "startup")
    verification = result.snapshot.entities[question.id]
    assert isinstance(verification, Verification)
    assert (verification.method, verification.result) == ("emulation", "UNKNOWN")
    scenario = question.data["scenario"]
    assert scenario["run_until"]["value"] == "2" and scenario["stimuli"][0]["input"] == "temperature"
    assert {entry.record["kind"] for entry in question.measures} == {
        "emulation.first_at", "emulation.uart_value", "emulation.count", "emulation.pin_config",
    }


def test_an_emulation_question_cannot_state_its_result():
    from fang.diagnostics import FangError
    from fang.emulation import Emulates, FirstAt, I2CRead

    with pytest.raises(FangError) as raised:
        Emulates("sensor_ready", measures={"first_read": FirstAt(I2CRead("env"))}, result="PASS")
    assert raised.value.diagnostic.code == "SIM-0002"


def test_an_emulation_question_routes_to_renode_at_the_behavioural_level():
    result = _elaborate(SENSOR_NODE.SensorNode)
    routed = route(result.snapshot, _question(result.snapshot, "startup"))
    assert (routed.level, routed.tool) == (Level.BEHAVIOURAL, "renode")


def test_preparing_a_job_records_the_firmware_and_the_plan():
    from fang.emulation import RENODE

    result = _elaborate(SENSOR_NODE.SensorNode)
    question = _question(result.snapshot, "startup")
    first = RENODE.prepare(result.snapshot, question, traits=result.traits)
    second = RENODE.prepare(result.snapshot, question, traits=result.traits)
    assert first.hash == second.hash
    assert set(first.inputs) == {"firmware/elf/sensor_node.elf"}
    assert first.extra["ran"] == "local" and first.extra["plan"].startswith("sha256:")
    assert first.extra["firmware_reports"] == "reported"
    assert first.confidence == Decimal("0.8")


def test_an_unrelated_change_to_the_snapshot_leaves_the_emulation_job_as_it_was(tmp_path):
    """A job's identity excludes the snapshot's own hash (RFC 12 section
    12.8): an entity the run does not read, or the checkout the program sits
    in, moves the snapshot and not the job, so a measurement stays current.
    A rebuilt firmware still moves it."""
    import shutil as _shutil

    from fang.cli import load_system
    from fang.emulation import RENODE
    from fang.entities import Evidence
    from fang.identity import derive

    result = _elaborate(SENSOR_NODE.SensorNode)
    question = _question(result.snapshot, "startup")
    note = Evidence(derive(result.snapshot.project_id, "evidence", "unrelated.note"), claim="a note")
    edited = result.snapshot.with_entities(
        {**result.snapshot.entities, note.id: note}, result.snapshot.revision_id
    )
    assert edited.hash != result.snapshot.hash
    before = RENODE.prepare(result.snapshot, question, traits=result.traits)
    after = RENODE.prepare(edited, question, traits=result.traits)
    assert after.snapshot == edited.hash
    assert after.files == before.files and after.extra == before.extra
    assert after.hash == before.hash

    copy = tmp_path / "sensor_node"
    _shutil.copytree(ROOT / "examples" / "sensor_node", copy, ignore=_shutil.ignore_patterns("out"))
    moved = _elaborate(load_system(copy / "sensor_node.py"))
    assert moved.snapshot.hash != result.snapshot.hash
    elsewhere = RENODE.prepare(moved.snapshot, _question(moved.snapshot, "startup"), traits=moved.traits)
    assert elsewhere.hash == before.hash

    firmware = copy / "firmware" / "elf" / "sensor_node.elf"
    firmware.write_bytes(firmware.read_bytes() + b"\0")
    rebuilt = RENODE.prepare(moved.snapshot, _question(moved.snapshot, "startup"), traits=moved.traits)
    assert rebuilt.hash != before.hash


def test_a_plan_the_board_cannot_satisfy_is_not_runnable_and_names_its_code():
    from fang.emulation import RENODE, Emulates, FirstAt, I2CRead

    class Unabstracted(SENSOR_NODE.SensorNode):
        startup = Emulates(
            "sensor_ready", run_until=2 * SENSOR_NODE.s,
            measures={"first_read": FirstAt(I2CRead("env"))},
        )

    result = _elaborate(Unabstracted)
    with pytest.raises(NotRunnable) as raised:
        RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    assert raised.value.code == "SIM-0010"
    assert "scl_pullup" in str(raised.value)


def _answered(system, attribute, tmp_path):
    result = _elaborate(system)
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    outcome = answer(graph, _question(graph.head, attribute), traits=result.traits, workspace=tmp_path)
    return graph, outcome


def _startup_with(firmware: str):
    from fang.emulation import Emulates

    original = SENSOR_NODE.SensorNode.startup

    class Variant(SENSOR_NODE.SensorNode):
        startup = Emulates(
            "sensor_ready", run_until=original.run_until, stimuli=original.stimuli,
            measures=original.measures, abstracted=original.abstracted, firmware=firmware,
        )

    return Variant


@needs_renode
def test_the_startup_question_passes_through_the_gate(tmp_path):
    graph, outcome = _answered(SENSOR_NODE.SensorNode, "startup", tmp_path)
    assert outcome.status == "answered"
    verification = graph.head.entities[outcome.question.id]
    assert verification.result == "PASS" and verification.tool == "renode"


@needs_renode
def test_the_wrong_address_build_fails_on_its_first_read(tmp_path):
    graph, outcome = _answered(_startup_with(str(ELF / "wrong_address.elf")), "startup", tmp_path)
    assert outcome.status == "failed"
    verification = graph.head.entities[outcome.question.id]
    assert verification.result == "FAIL"
    evidence = graph.head.entities[verification.evidence[0]]
    first_read = next(m for m in evidence.extensions["measurement"]["measures"] if m["name"] == "first_read")
    assert first_read["max"] == "Infinity"


@needs_renode
def test_the_push_pull_build_fails_on_pin_configuration(tmp_path):
    graph, outcome = _answered(_startup_with(str(ELF / "push_pull.elf")), "startup", tmp_path)
    evidence = graph.head.entities[graph.head.entities[outcome.question.id].evidence[0]]
    mux = next(m for m in evidence.extensions["measurement"]["measures"] if m["name"] == "mux_mismatches")
    assert outcome.status == "failed" and mux["value"] == "2"


@needs_renode
def test_the_led_on_another_pin_fails_its_blink_count(tmp_path):
    from fang.interfaces import Pin, PinMap

    class Rewired(SENSOR_NODE.STM32F401RE):
        PA6 = Pin("PA6", role="data", number="22")
        pinmap = PinMap(
            {"power.vcc": "VDD", "power.gnd": "VSS", "status.line": "PA6"}, evidence="pinout"
        )

    # The firmware path resolves against the program that declares the part,
    # which here is this test, so the build is named by its absolute path.
    class MovedLed(_startup_with(str(ELF / "sensor_node.elf"))):
        mcu = Rewired(package="LQFP-64")

    graph, outcome = _answered(MovedLed, "startup", tmp_path)
    evidence = graph.head.entities[graph.head.entities[outcome.question.id].evidence[0]]
    blinks = next(m for m in evidence.extensions["measurement"]["measures"] if m["name"] == "slow_blinks")
    assert outcome.status == "failed" and blinks["value"] == "0"


@needs_renode
def test_the_no_timeout_build_fails_the_missing_sensor_question(tmp_path):
    from fang.emulation import Emulates

    original = SENSOR_NODE.SensorNode.sensor_missing

    class NoTimeout(SENSOR_NODE.SensorNode):
        sensor_missing = Emulates(
            "survives_missing_sensor", run_until=original.run_until, faults=original.faults,
            measures=original.measures, abstracted=original.abstracted,
            firmware=str(ELF / "no_timeout.elf"),
        )

    graph, outcome = _answered(NoTimeout, "sensor_missing", tmp_path)
    assert outcome.status == "failed"


@needs_renode
def test_a_rebuilt_firmware_makes_its_verification_stale(tmp_path):
    import shutil as _shutil

    from fang.cli import load_system
    from fang.emulation import stale

    copy = tmp_path / "sensor_node"
    _shutil.copytree(ROOT / "examples" / "sensor_node", copy, ignore=_shutil.ignore_patterns("out"))
    system = load_system(copy / "sensor_node.py")
    graph, outcome = _answered(system, "startup", tmp_path / "runs")
    assert outcome.status == "answered" and stale(graph.head) == ()
    firmware = copy / "firmware" / "elf" / "sensor_node.elf"
    firmware.write_bytes(firmware.read_bytes() + b"\0")
    (label, path, recorded, current) = next(s for s in stale(graph.head) if s[0].endswith("startup"))
    assert path == "firmware/elf/sensor_node.elf" and recorded != current


def test_a_run_past_its_limit_is_ended_with_every_process_it_started(tmp_path):
    """The kill is the operating system's, not Renode's, so it is checked on
    every machine, Windows included, with a stand-in: a parent that starts a
    child, and the child writing a heartbeat. Ending the run ends both, and
    the heartbeat stops."""
    import sys
    import time

    from fang.renode.backend import _kill_group, _new_group

    beat = tmp_path / "beat"
    child = (
        "import time\n"
        "while True:\n"
        f"    open({str(beat)!r}, 'a').write('.')\n"
        "    time.sleep(0.05)\n"
    )
    parent = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        "time.sleep(120)\n"
    )
    process = subprocess.Popen([sys.executable, "-c", parent], **_new_group())
    deadline = time.monotonic() + 30
    while not (beat.exists() and beat.stat().st_size > 2):
        if time.monotonic() > deadline:
            _kill_group(process)
            pytest.fail("the stand-in child never started")
        time.sleep(0.05)

    _kill_group(process)
    assert process.returncode is not None
    time.sleep(0.3)             # a write already in flight may still land
    size = beat.stat().st_size
    time.sleep(0.5)
    assert beat.stat().st_size == size, "a process the run started outlived it"


@needs_renode
def test_a_hung_run_is_ended_whole_and_keeps_its_partial_events():
    p = plan(run_until_ns=3_600_000_000_000)
    run = RenodeBackend().run(bundle(p, (ELF / "sensor_node.elf").read_bytes()), timeout=12)
    assert run.outcome == "timeout" and run.exit_status is None
    if shutil.which("pgrep"):
        survivors = subprocess.run(["pgrep", "-f", "fang-renode-"], capture_output=True, text=True).stdout
        assert survivors.strip() == ""
    measured_run = measure(p, run_record(run.events, run.outcome))
    assert all(m.quantity is None for m in measured_run)


# -- the commands ----------------------------------------------------------------


def _cli(*argv):
    from fang.cli import main

    return main(list(argv))


def test_emulate_writes_a_bundle_without_running_anything(tmp_path, capsys):
    program = str(ROOT / "examples" / "sensor_node" / "sensor_node.py")
    assert _cli("emulate", program, "--bundle-only", "-o", str(tmp_path)) == 0
    printed = capsys.readouterr().out
    assert "renode 1.17.0" not in printed and "plan sha256:" in printed
    written = {p.name for p in (tmp_path / "startup").iterdir()}
    assert written == {"plan.json", "platform.repl", "run.resc", "fang_probes.cs",
                       "stm32f401re.repl", "firmware.elf", "manifest.json"}


def test_emulate_on_a_program_with_no_emulation_question_says_so(capsys):
    assert _cli("emulate", str(ROOT / "examples" / "divider" / "divider.py")) == 0
    assert "declares no emulation question" in capsys.readouterr().out


@needs_renode
def test_emulate_prints_what_the_run_measured(capsys):
    assert _cli("emulate", str(ROOT / "examples" / "sensor_node" / "sensor_node.py")) == 0
    printed = capsys.readouterr().out
    assert "first_read = 0.0400 s" in printed and "fast_blinks = 5" in printed


def test_the_evidence_names_every_file_the_run_is_given():
    from fang.emulation import RENODE

    result = _elaborate(SENSOR_NODE.SensorNode)
    job = RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    named = dict(entry.split(" ") for entry in job.extra["bundle"].split(", "))
    assert set(named) == set(job.files)
    assert all(digest.startswith("sha256:") for digest in named.values())


def test_an_emulator_of_an_unchecked_version_reports_unsupported():
    from fang.emulation import RenodeTool
    from fang.renode import RenodeBackend
    from fang.verification import ToolUnavailable

    class Newer(RenodeBackend):
        def available(self):
            return True

        def identify(self):
            return "1.18.0", "1.18.0+20270101gitdeadbeef"

    tool = RenodeTool(backend=Newer())
    # Installed, so not reported missing; its version is what it is refused for.
    assert tool.available()
    with pytest.raises(ToolUnavailable, match="1.18.0.*1.17.0"):
        tool.version()


def test_an_unchecked_version_is_reported_unsupported_by_version_through_verify(tmp_path):
    # available() used to fold the version in, so `answer` said "renode is
    # not installed" and never reached the version it was refused for.
    from fang.emulation import RenodeTool
    from fang.renode import RenodeBackend
    from fang.verification import ToolRegistry

    class Newer(RenodeBackend):
        def available(self):
            return True

        def identify(self):
            return "1.18.0", "1.18.0+20270101gitdeadbeef"

    result = _elaborate(SENSOR_NODE.SensorNode)
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    tools = ToolRegistry((RenodeTool(backend=Newer()),))
    outcome = answer(graph, _question(graph.head, "startup"), traits=result.traits, tools=tools, workspace=tmp_path)
    assert outcome.status == "unsupported"
    assert "1.18.0" in outcome.message and "1.17.0" in outcome.message
    assert "not installed" not in outcome.message
    assert graph.head.hash == result.snapshot.hash


def test_a_missing_emulator_is_reported_unsupported_through_verify(tmp_path):
    from fang.emulation import RenodeTool
    from fang.renode import RenodeBackend
    from fang.verification import ToolRegistry

    result = _elaborate(SENSOR_NODE.SensorNode)
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    tools = ToolRegistry((RenodeTool(backend=RenodeBackend(executable="renode-is-not-here")),))
    outcome = answer(graph, _question(graph.head, "startup"), traits=result.traits, tools=tools, workspace=tmp_path)
    assert outcome.status == "unsupported" and "renode" in outcome.message
    assert graph.head.hash == result.snapshot.hash


def test_a_pin_the_platform_model_does_not_map_refuses_the_plan(monkeypatch):
    from fang.emulation import EmulationError, compile_plan, descriptor

    result, paths = _board()
    platform = descriptor("fang:stm32f401re")
    pins = {k: v for k, v in platform.document["pins"].items() if k != "PB8"}
    monkeypatch.setitem(platform.document, "pins", pins)
    with pytest.raises(EmulationError, match="PB8") as refused:
        compile_plan(result.snapshot, _Question(_startup_data(paths)), traits=result.traits)
    assert refused.value.code == "pin"


def test_rebuilding_the_firmware_leaves_the_snapshot_byte_identical(tmp_path):
    import shutil as _shutil

    from fang.cli import load_system

    copy = tmp_path / "sensor_node"
    _shutil.copytree(ROOT / "examples" / "sensor_node", copy, ignore=_shutil.ignore_patterns("out"))
    before = _elaborate(load_system(copy / "sensor_node.py")).snapshot
    firmware = copy / "firmware" / "elf" / "sensor_node.elf"
    firmware.write_bytes(firmware.read_bytes() + b"\0")
    after = _elaborate(load_system(copy / "sensor_node.py")).snapshot
    assert after.hash == before.hash


# -- what a plan refuses rather than measuring as nothing ------------------------


def _with_measure(data, name, unit, measure):
    """The startup question's data with one more measure."""
    data["measures"] = [*data["measures"], {"name": name, "parameter": f"X.{name}", "unit": unit, "measure": measure}]
    return data


@pytest.mark.parametrize("surface", ["mcu.status", "mcu.usart2"])
def test_a_pin_configuration_over_a_port_that_is_no_bus_is_refused(surface):
    # It used to measure 0 having checked no pin, so `== 0` passed.
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    data = _with_measure(_startup_data(paths), "elsewhere", "1",
                         {"kind": "emulation.pin_config", "surface": surface})
    with pytest.raises(EmulationError, match=surface.replace(".", r"\.")) as refused:
        compile_plan(result.snapshot, _Question(data), traits=result.traits)
    assert refused.value.code == "bus"


def test_a_pin_configuration_over_an_i2c_port_with_nothing_on_it_is_refused():
    from fang.emulation import RENODE, Emulates, PinConfig
    from fang.lang import s

    class Unwired(SENSOR_NODE.SensorNode):
        startup = Emulates("sensor_ready", run_until=2 * s, measures={"mux_mismatches": PinConfig("mcu.i2c1")},
                           abstracted=("series", "console"))
        sensor_missing = None

        def architecture(self):
            self.header.dc >> self.mcu.power
            self.header.dc >> self.env.power
            self.mcu.usart2 >> self.console.uart
            self.header.dc.gnd >> self.console.ground
            self.mcu.status >> self.series.p1
            self.series.p2 >> self.indicator.p1
            self.indicator.p2 >> self.header.dc.gnd

    result = _elaborate(Unwired)
    with pytest.raises(NotRunnable) as refused:
        RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    assert refused.value.code == "SIM-0016" and "mcu.i2c1" in str(refused.value)


@pytest.mark.parametrize(
    "match",
    [
        {"kind": "i2c.read", "surface": "env", "detail": {"register": 0}},
        {"kind": "uart.line", "surface": "mcu.usart2", "detail": {"starts": "temp="}},
    ],
)
def test_a_match_detail_no_measure_reads_is_refused(match):
    # I2CRead("env", register=0) matched every read of the sensor, whatever
    # register it named: the plan carried the detail and nothing read it.
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    data = _with_measure(_startup_data(paths), "filtered", "1",
                         {"kind": "emulation.count", "surface": match["surface"], "match": match})
    detail = next(iter(match["detail"]))
    with pytest.raises(EmulationError, match=detail) as refused:
        compile_plan(result.snapshot, _Question(data), traits=result.traits)
    assert refused.value.code == "measure"


def test_the_details_a_measure_reads_still_compile():
    from fang.emulation import compile_plan

    result, paths = _board()
    data = _with_measure(_startup_data(paths), "temps", "1", {
        "kind": "emulation.count", "surface": "mcu.usart2",
        "match": {"kind": "uart.line", "surface": "mcu.usart2", "detail": {"contains": "temp="}},
    })
    plan = compile_plan(result.snapshot, _Question(data), traits=result.traits)
    assert plan.measures["temps"]["matches"][0]["detail"] == {"contains": "temp="}


def test_a_reversed_count_window_is_refused_where_it_is_declared():
    # (2 s, 1 s) counted nothing, and `== 0` passed over an empty window.
    from fang.diagnostics import FangError
    from fang.emulation import Count, Rises
    from fang.lang import s

    with pytest.raises(FangError) as refused:
        Count(Rises("mcu.status"), within=(2 * s, 1 * s))
    assert refused.value.diagnostic.code == "SIM-0003" and "2 s" in str(refused.value)
    assert refused.value.diagnostic.location.file == __file__
    with pytest.raises(FangError):
        Count(Rises("mcu.status"), within=(1 * s, 1 * s))


def test_a_count_window_bounded_by_anything_but_times_is_refused():
    # (1 V, 2 V) was read as one second to two.
    from fang.diagnostics import FangError
    from fang.emulation import Count, Rises
    from fang.lang import V, s

    with pytest.raises(FangError) as refused:
        Count(Rises("mcu.status"), within=(1 * V, 2 * V))
    assert refused.value.diagnostic.code == "UNIT-0001" and "1 V" in str(refused.value)
    with pytest.raises(FangError):
        Count(Rises("mcu.status"), within=(1 * s, 2 * V))


def test_a_reversed_window_in_a_question_is_refused_when_it_compiles():
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    data = _startup_data(paths)
    blinks = next(m for m in data["measures"] if m["name"] == "slow_blinks")
    blinks["measure"]["within_ns"] = [2_000_000_000, 1_000_000_000]
    with pytest.raises(EmulationError, match="slow_blinks") as refused:
        compile_plan(result.snapshot, _Question(data), traits=result.traits)
    assert refused.value.code == "measure"


class _Crashes(RenodeBackend):
    """A Renode that reports 1.17.0 and whose every run crashes at once: enough
    for a run's evidence to be recorded, with no emulator installed."""

    def available(self):
        return True

    def identify(self):
        return "1.17.0", "1.17.0+stand-in"

    def run(self, files, *, timeout=120):
        from fang.renode import RenodeRun

        return RenodeRun("1.17.0", "1.17.0+stand-in", 1, "crashed", b"", "", ())


def _stand_in_tools(backend=None):
    from fang.emulation import RenodeTool
    from fang.verification import ToolRegistry

    return ToolRegistry((RenodeTool(backend=backend or _Crashes()),))


def test_staleness_resolves_the_firmware_where_the_run_does(tmp_path):
    """A run reads the bound firmware relative to the program that declares
    the part; staleness used to read it relative to the question's program,
    so a question redeclared in another directory read as stale at once and
    then missed a rebuild."""
    import shutil as _shutil

    from fang.cli import load_system
    from fang.emulation import Emulates, stale

    copy = tmp_path / "sensor_node"
    _shutil.copytree(ROOT / "examples" / "sensor_node", copy, ignore=_shutil.ignore_patterns("out"))
    board = load_system(copy / "sensor_node.py")
    original = board.startup

    class Elsewhere(board):          # declared here, in tests/, not beside the part
        startup = Emulates(
            "sensor_ready", run_until=original.run_until, stimuli=original.stimuli,
            measures=original.measures, abstracted=original.abstracted,
        )

    result = _elaborate(Elsewhere)
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    question = _question(graph.head, "startup")
    answer(graph, question, traits=result.traits, tools=_stand_in_tools(), workspace=tmp_path / "runs")
    assert graph.head.entities[question.id].evidence
    assert stale(graph.head) == ()

    firmware = copy / "firmware" / "elf" / "sensor_node.elf"
    firmware.write_bytes(firmware.read_bytes() + b"\0")
    ((label, path, recorded, current),) = stale(graph.head)
    assert label.endswith("startup") and path == "firmware/elf/sensor_node.elf"
    assert current.startswith("sha256:") and current != recorded


def test_a_signal_with_two_loads_is_observed_on_its_one_pin():
    # Each port link listed PA5 again, so the plan refused the status signal
    # as landing on 2 pins of the target.
    from fang.emulation import RENODE, Emulates
    from fang.lang import kOhm
    from fang.parts import Resistor

    original = SENSOR_NODE.SensorNode.startup

    class TwoLoads(SENSOR_NODE.SensorNode):
        probe_load = Resistor(resistance=10 * kOhm, package="R_0402")
        startup = Emulates(
            "sensor_ready", run_until=original.run_until, stimuli=original.stimuli,
            measures=original.measures, abstracted=(*original.abstracted, "probe_load"),
        )

        def architecture(self):
            super().architecture()
            self.mcu.status >> self.probe_load.p1
            self.probe_load.p2 >> self.header.dc.gnd

    result = _elaborate(TwoLoads)
    job = RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    import json as _json

    (gpio,) = [o for o in _json.loads(job.files["plan.json"])["observations"] if o["kind"] == "gpio"]
    assert (gpio["emulator"], gpio["index"]) == ("gpioPortA", 5)


def test_a_read_of_a_device_a_fault_removes_is_refused():
    # An absent device gets no probe, so a count of its reads was 0 and a
    # first read was never, whatever the firmware did.
    from fang.emulation import RENODE, Count, Emulates, I2CRead

    original = SENSOR_NODE.SensorNode.sensor_missing

    class CountsReads(SENSOR_NODE.SensorNode):
        missing_reads = SENSOR_NODE.Parameter("", description="reads of the sensor while it is missing")
        sensor_missing = Emulates(
            "survives_missing_sensor", run_until=original.run_until, faults=original.faults,
            measures={**original.measures, "missing_reads": Count(I2CRead("env"))},
            abstracted=original.abstracted,
        )

    result = _elaborate(CountsReads)
    with pytest.raises(NotRunnable) as refused:
        RENODE.prepare(result.snapshot, _question(result.snapshot, "sensor_missing"), traits=result.traits)
    assert refused.value.code == "SIM-0003"
    assert "missing_reads" in str(refused.value) and "absent" in str(refused.value)


def test_a_stimulus_on_a_device_a_fault_removes_is_refused():
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    data = _startup_data(paths, faults=[{"kind": "absent", "surface": "env"}])
    data["measures"] = [m for m in data["measures"] if m["name"] != "first_read"]
    with pytest.raises(EmulationError, match="absent") as refused:
        compile_plan(result.snapshot, _Question(data), traits=result.traits)
    assert refused.value.code == "stimulus"


def test_the_missing_sensor_question_measures_only_what_the_firmware_does():
    result = _elaborate(SENSOR_NODE.SensorNode)
    question = _question(result.snapshot, "sensor_missing")
    assert [entry.name for entry in question.measures] == ["fast_blinks"]


def test_emulate_reports_an_unchecked_version_and_runs_nothing(monkeypatch, capsys):
    from fang.emulation import RENODE

    class Newer(RenodeBackend):
        def available(self):
            return True

        def identify(self):
            return "1.18.0", "1.18.0+20270101gitdeadbeef"

        def run(self, files, *, timeout=120):
            raise AssertionError("nothing runs on an unchecked version")

    monkeypatch.setattr(RENODE, "backend", Newer())
    assert _cli("emulate", str(ROOT / "examples" / "sensor_node" / "sensor_node.py")) == 0
    printed = capsys.readouterr().out
    assert "unsupported: Renode 1.18.0 is installed" in printed


@pytest.mark.parametrize("outcome", ["timeout", "crashed"])
def test_emulate_fails_when_a_run_does_not_complete(monkeypatch, capsys, outcome):
    # It exited 0, so a script read a hung or crashed run as a success.
    from fang.emulation import RENODE
    from fang.renode import RenodeRun

    class Ends(_Crashes):
        def run(self, files, *, timeout=120):
            return RenodeRun("1.17.0", "1.17.0+stand-in", None if outcome == "timeout" else 1,
                             outcome, b"", "", ())

    monkeypatch.setattr(RENODE, "backend", Ends())
    assert _cli("emulate", str(ROOT / "examples" / "sensor_node" / "sensor_node.py")) == 1
    printed = capsys.readouterr().out
    assert f"the run {outcome}" in printed and "first_read: no value" in printed


class _Logs(_Crashes):
    """A Renode whose every run crashes having logged a line: a run worth
    keeping, since its log is how the crash is read."""

    def run(self, files, *, timeout=120):
        from fang.renode import RenodeRun

        return RenodeRun("1.17.0", "1.17.0+stand-in", 1, "crashed", b"", "the stand-in crashed\n",
                         ("renode", "--console", "--disable-gui", "-p", "run.resc"))


def test_a_run_keeps_its_bundle_and_what_it_left_in_its_workspace(tmp_path):
    # The run happened in a temporary directory deleted on return, so a run
    # made under verify --commit kept neither its bundle nor its log.
    import json as _json

    from fang.emulation import RENODE, RenodeTool

    result = _elaborate(SENSOR_NODE.SensorNode)
    job = RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    kept = tmp_path / "renode-run"
    RenodeTool(backend=_Logs()).run(job, workspace=kept)
    for name, content in job.files.items():
        assert (kept / name).read_bytes() == (content.encode("utf-8") if isinstance(content, str) else content)
    assert (kept / "events.jsonl").read_bytes() == b""
    assert (kept / "renode.log").read_text(encoding="utf-8") == "the stand-in crashed\n"
    ended = _json.loads((kept / "outcome.json").read_text(encoding="utf-8"))
    assert ended["outcome"] == "crashed" and ended["exit_status"] == 1
    assert ended["renode"] == {"version": "1.17.0", "build": "1.17.0+stand-in"}


def test_a_run_that_cannot_be_made_keeps_nothing(monkeypatch, tmp_path):
    from fang.emulation import RENODE, RenodeTool
    from fang.verification import ToolUnavailable

    class Checked(RenodeBackend):
        def available(self):
            return True

        def identify(self):
            return "1.17.0", "1.17.0+stand-in"

    result = _elaborate(SENSOR_NODE.SensorNode)
    job = RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    _spaced_tmpdir(monkeypatch, tmp_path)
    with pytest.raises(ToolUnavailable):
        RenodeTool(backend=Checked()).run(job, workspace=tmp_path / "renode-run")
    assert not (tmp_path / "renode-run").exists()


def test_verify_commit_keeps_each_run_and_verify_alone_keeps_none(monkeypatch, tmp_path, capsys):
    import shutil as _shutil

    from fang.emulation import RENODE

    copy = tmp_path / "sensor_node"
    _shutil.copytree(ROOT / "examples" / "sensor_node", copy, ignore=_shutil.ignore_patterns("out"))
    program = str(copy / "sensor_node.py")
    assert _cli("build", program, "-C", str(copy)) == 0
    monkeypatch.setattr(RENODE, "backend", _Logs())
    runs = copy / ".copperhead" / "simulations"

    _cli("verify", program, "-C", str(copy))
    assert not any(runs.iterdir())

    _cli("verify", program, "-C", str(copy), "--commit")
    logs = sorted(runs.glob("renode-*/renode.log"))
    assert len(logs) == 2
    for log in logs:
        assert log.read_text(encoding="utf-8") == "the stand-in crashed\n"
        assert {"events.jsonl", "outcome.json", "plan.json", "run.resc", "firmware.elf"} <= {
            p.name for p in log.parent.iterdir()
        }
    capsys.readouterr()


def _spaced_tmpdir(monkeypatch, tmp_path):
    """TMPDIR set to a path with a space in it, as tempfile reads it afresh."""
    import tempfile

    spaced = tmp_path / "with space"
    spaced.mkdir()
    monkeypatch.setenv("TMPDIR", str(spaced))
    monkeypatch.setattr(tempfile, "tempdir", None)
    return spaced


def test_a_scratch_path_with_a_space_is_reported_before_anything_runs(monkeypatch, tmp_path):
    # Renode's monitor splits `i $CWD/run.resc` at the space and the run
    # crashed with no events; it is now refused by name before Renode starts.
    from fang.renode import RenodeUnavailable

    class Checked(RenodeBackend):
        def available(self):
            return True

        def identify(self):
            return "1.17.0", "1.17.0+stand-in"

    def never(*args, **kwargs):
        raise AssertionError("Renode was started")

    _spaced_tmpdir(monkeypatch, tmp_path)
    monkeypatch.setattr(subprocess, "Popen", never)
    with pytest.raises(RenodeUnavailable, match="renode.*space"):
        Checked().run(bundle(plan(), b"\0"), timeout=5)


def test_a_scratch_path_with_a_space_is_reported_unsupported_through_verify(monkeypatch, tmp_path):
    class Checked(RenodeBackend):
        def available(self):
            return True

        def identify(self):
            return "1.17.0", "1.17.0+stand-in"

    result = _elaborate(SENSOR_NODE.SensorNode)
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    _spaced_tmpdir(monkeypatch, tmp_path)
    outcome = answer(graph, _question(graph.head, "startup"), traits=result.traits,
                     tools=_stand_in_tools(Checked()), workspace=tmp_path / "runs")
    assert outcome.status == "unsupported" and "space" in outcome.message
    assert graph.head.hash == result.snapshot.hash


@pytest.mark.parametrize(
    "quantity",
    [
        {"kind": "range", "unit": "degC", "min": "20", "max": "30"},
        {"kind": "tolerance", "unit": "degC", "nominal": "25", "tolerance": {"kind": "relative", "value": "1"}},
    ],
)
def test_a_stimulus_of_more_than_one_value_is_refused(quantity):
    # The conversion's value was None, and the plan raised AttributeError.
    from fang.emulation import EmulationError, compile_plan

    result, paths = _board()
    stimuli = [{"at": _scalar("0", "ms"), "surface": "env", "input": "temperature", "quantity": quantity}]
    with pytest.raises(EmulationError, match="temperature") as refused:
        compile_plan(result.snapshot, _Question(_startup_data(paths, stimuli=stimuli)), traits=result.traits)
    assert refused.value.code == "stimulus"


def test_a_ranged_stimulus_leaves_verify_standing(tmp_path):
    # answer() catches only NotRunnable, so the AttributeError ended fang verify.
    from fang.emulation import At, Emulates
    from fang.units import Quantity
    from fang.verification import NOT_RUNNABLE

    original = SENSOR_NODE.SensorNode.startup

    class Ranged(SENSOR_NODE.SensorNode):
        startup = Emulates(
            "sensor_ready", run_until=original.run_until,
            stimuli=[At(0 * SENSOR_NODE.ms, "env.temperature", Quantity.range(20, 30, "degC"))],
            measures=original.measures, abstracted=original.abstracted,
        )

    result = _elaborate(Ranged)
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    outcome = answer(graph, _question(graph.head, "startup"), traits=result.traits,
                     tools=_stand_in_tools(), workspace=tmp_path)
    assert outcome.status == NOT_RUNNABLE and "temperature" in outcome.message


@pytest.mark.parametrize("at", [_scalar("3", "s"), _scalar("-1", "ms")])
def test_a_stimulus_outside_the_run_is_refused_as_a_stimulus(at):
    # One after the run's end was refused by the lowering, as SIM-0003 "a
    # surface or part that resolves to no pins".
    from fang.emulation import RENODE, At, Emulates
    from fang.units import Quantity

    original = SENSOR_NODE.SensorNode.startup

    class Late(SENSOR_NODE.SensorNode):
        startup = Emulates(
            "sensor_ready", run_until=original.run_until,
            stimuli=[At(Quantity.from_dict(at), "env.temperature", 25 * SENSOR_NODE.degC)],
            measures=original.measures, abstracted=original.abstracted,
        )

    result = _elaborate(Late)
    with pytest.raises(NotRunnable) as refused:
        RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    assert refused.value.code == "SIM-0012" and "env.temperature" in str(refused.value)


@pytest.mark.parametrize("part", ["system.env", "system.mcu"])
def test_a_model_naming_no_shipped_descriptor_refuses_the_plan_naming_the_part(part):
    from fang.emulation import EmulationError, EmulationModel, compile_plan

    result, paths = _board()
    result.traits.attach(paths[part], EmulationModel(source="renode:Sensors.Generic"))
    with pytest.raises(EmulationError) as refused:
        compile_plan(result.snapshot, _Question(_startup_data(paths)), traits=result.traits)
    assert refused.value.code == "model"
    assert part in str(refused.value) and "renode:Sensors.Generic" in str(refused.value)


def test_an_address_that_is_no_whole_number_refuses_the_plan():
    # 72.5 was made 72 by int(), so Renode answered at an address the graph
    # does not hold.
    from fang.emulation import RENODE
    from fang.interfaces import I2CPort
    from fang.lang import V, kHz, kOhm

    class HalfAddressed(SENSOR_NODE.HS3001):
        i2c = I2CPort(address=72.5 * SENSOR_NODE.addr, voltage=3.3 * V, bit_rate=400 * kHz,
                      pull_up_resistance=2.2 * kOhm, pull_up_supply=3.3 * V)

    class Board(SENSOR_NODE.SensorNode):
        env = HalfAddressed(package="LGA-6")

    result = _elaborate(Board)
    with pytest.raises(NotRunnable) as refused:
        RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    assert refused.value.code == "SIM-0016"
    assert "system.env" in str(refused.value) and "72.5" in str(refused.value)


def test_a_selector_the_platform_does_not_read_refuses_the_plan():
    # "AF_4" read as no alternate function, so PinConfig skipped the AFR
    # comparison and measured 0 whatever the firmware wrote there.
    from fang.emulation import RENODE
    from fang.interfaces import AF, PinMap, Selector

    class Misspelt(SENSOR_NODE.STM32F401RE):
        peripherals = PinMap(
            {
                "i2c1.scl": {"PB8": Selector("AF_4"), "PB6": AF(4)},
                "i2c1.sda": {"PB9": AF(4), "PB7": AF(4)},
                "usart2.tx": {"PA2": AF(7)},
                "usart2.rx": {"PA3": AF(7)},
            },
            evidence="af_table",
        )

    class Board(SENSOR_NODE.SensorNode):
        mcu = Misspelt(package="LQFP-64")

    result = _elaborate(Board)
    with pytest.raises(NotRunnable) as refused:
        RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    assert refused.value.code == "SIM-0013"
    assert "PB8" in str(refused.value) and "'AF_4'" in str(refused.value)


@pytest.mark.parametrize("selector", ["AF_4", "AF16"])
def test_a_pin_configuration_over_a_selector_the_platform_does_not_read_has_no_value(selector):
    p = plan()
    (bus,) = p.buses
    scl, sda = bus.pins
    misspelt = PlanPin(scl.pin, scl.vendor, scl.signal, selector, scl.open_drain, scl.port, scl.index)
    unread = EmulationPlan(**{**p.__dict__, "buses": (PlanBus(bus.port, bus.instance, bus.emulator,
                                                              (misspelt, sda), bus.devices),)})
    mux = measured(unread, recorded("startup"))["mux_mismatches"]
    assert mux.quantity is None and selector in mux.reason and "PB8" in mux.reason


def test_a_model_naming_no_shipped_descriptor_is_sim_0009_through_prepare():
    from fang.emulation import RENODE, EmulationModel

    class Generic(SENSOR_NODE.SensorNode):
        def __init__(self, **overrides):
            super().__init__(**overrides)
            self.env.add_trait(EmulationModel(source="renode:Sensors.Generic"))

    result = _elaborate(Generic)
    with pytest.raises(NotRunnable) as refused:
        RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    assert refused.value.code == "SIM-0009" and "system.env" in str(refused.value)


def test_a_device_probe_is_named_by_the_devices_whole_path():
    # Only the last segment was kept, so a.env and b.env were both fang_env,
    # and Renode refused the second as already declared.
    import re as _re

    from fang.emulation import _probe_name, compile_plan

    result, paths = _board()
    plan_ = compile_plan(result.snapshot, _Question(_startup_data(paths)), traits=result.traits)
    assert plan_.device(paths["system.env"]).probe == "fang_system_env"
    assert _probe_name("system.a.env") != _probe_name("system.b.env")
    assert _re.fullmatch(r"fang_[A-Za-z0-9_]+", _probe_name("system.a.env"))


def test_two_probes_of_one_name_are_refused_by_the_lowering():
    p = plan()
    (bus,) = p.buses
    twin = PlanDevice("env2", "env", "renode:Sensors.HS3001", "Antmicro.Renode.Peripherals.Sensors.HS3001", 0x45)
    doubled = EmulationPlan(**{**p.__dict__, "buses": (PlanBus(bus.port, bus.instance, bus.emulator, bus.pins,
                                                               (*bus.devices, twin)),)})
    with pytest.raises(LoweringError, match="'env'"):
        platform_description(doubled)
    clash = PlanObservation("i2c1Warnings", "gpio", "mcu.status", "mcu.status", "gpioPortA", 5)
    with pytest.raises(LoweringError, match="i2c1Warnings"):
        platform_description(EmulationPlan(**{**p.__dict__, "observations": (clash,)}))


def test_a_uart_value_is_read_whole_with_its_exponent():
    """`temp=1.2e3` is 1200, not 1.2; and a number with something numeric
    run on after it is no number fang reads, rather than a prefix of one."""
    import dataclasses

    from fang.units import Quantity

    def reported(text: str):
        events = tuple(
            dataclasses.replace(e, payload={"text": text})
            if e.type == "uart.line" and e.payload.get("text", "").startswith("temp=") else e
            for e in recorded("startup").events
        )
        return measured(plan(), RunRecord(events, "completed"))["reported"]

    assert reported("temp=1.2e3").quantity == Quantity.scalar(Decimal("1.2e3"), "degC")
    assert reported("temp=25.01").quantity == Quantity.scalar(Decimal("25.01"), "degC")
    assert reported("temp=25.01 C").quantity == Quantity.scalar(Decimal("25.01"), "degC")
    for runon in ("temp=25.0.1", "temp=25x", "temp=1.2e"):
        unread = reported(runon)
        assert unread.quantity is None and "reads whole" in unread.reason, runon


def test_a_negative_address_refuses_the_plan():
    from fang.emulation import RENODE
    from fang.interfaces import I2CPort
    from fang.lang import V, kHz, kOhm

    class Negative(SENSOR_NODE.HS3001):
        i2c = I2CPort(address=-1 * SENSOR_NODE.addr, voltage=3.3 * V, bit_rate=400 * kHz,
                      pull_up_resistance=2.2 * kOhm, pull_up_supply=3.3 * V)

    class Board(SENSOR_NODE.SensorNode):
        env = Negative(package="LGA-6")

    result = _elaborate(Board)
    with pytest.raises(NotRunnable) as refused:
        RENODE.prepare(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    assert refused.value.code == "SIM-0016"
    assert "not negative" in str(refused.value)


def test_a_circuit_measure_on_a_surface_of_several_signals_names_its_signal():
    """An I2C port carries SCL and SDA: measuring `env.i2c` without naming
    one would probe whichever was declared first."""
    from fang import diagnostics
    from fang.elaborate import elaborate
    from fang.lang import Parameter, ms
    from fang.verification import Average, Simulates

    class Probed(SENSOR_NODE.SensorNode):
        bus_voltage = Parameter("V")
        probe = Simulates(
            "sensor_ready",
            measures={"bus_voltage": Average("env.i2c", after=0 * ms, until=1 * ms)},
        )

    result = elaborate(Probed, project_id="PRJ-EXAMPLES")
    assert not result.ok
    assert result.diagnostics[0].code == diagnostics.SIM_UNRESOLVED_SURFACE
    assert "several signals" in result.diagnostics[0].message

    class Named(SENSOR_NODE.SensorNode):
        bus_voltage = Parameter("V")
        probe = Simulates(
            "sensor_ready",
            measures={"bus_voltage": Average("env.i2c.sda", after=0 * ms, until=1 * ms)},
        )

    assert elaborate(Named, project_id="PRJ-EXAMPLES").ok


def test_a_plan_is_read_back_by_its_schema():
    """v2 is v1 without the snapshot. A v1 plan, snapshot and all, still
    reads; a plan of a schema fang does not know is refused by its label."""
    from fang.emulation import PLAN_SCHEMA, plan_from_dict

    written = plan().as_dict()
    assert written["schema"] == PLAN_SCHEMA == "fang.emulation/v2"
    assert "snapshot" not in written
    assert plan_from_dict(written).hash == plan().hash

    # A v1 plan keeps the schema it was written in, so its identity and hash
    # are the ones its bundle recorded, not those of the v2 plan it resembles.
    from dataclasses import replace

    v1 = replace(plan(), schema="fang.emulation/v1")
    older = dict(v1.as_dict(), snapshot="sha256:" + "0" * 64)
    read = plan_from_dict(older)
    assert read.schema == "fang.emulation/v1"
    assert read.hash == v1.hash == older["plan"]
    assert read.hash != plan().hash

    with pytest.raises(ValueError, match="fang.emulation/v3"):
        plan_from_dict(dict(written, schema="fang.emulation/v3"))
