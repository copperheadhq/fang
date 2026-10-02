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
        expected_warnings=tuple(descriptor("fang:stm32f401re").expected_warnings),
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
    assert moved.as_dict() != p.as_dict()


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
