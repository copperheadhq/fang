"""Spec: "Emulation Models Declare What They Cover", "Emulation Questions Are
Declared", "The Emulation Plan Resolves Everything Before Anything Runs",
"Fuses Set An AVR Part's Clock And Are Stated", "Registers An Engine Does Not
Model Are Watched", "The Fraction Of A Window A Pin Spends At A Level Is
Measured", and the emulation requirements as they reach a second emulator.

simavr runs the AVR cores Renode does not model. Engines, plans, the lowering
and the measures are pure, so most of this runs without simavr; the tests that
build and run the runner skip by name where simavr or a C compiler is not
installed.
"""

import dataclasses
import importlib.util
import json
from pathlib import Path

import pytest

from fang.emulation import (
    RENODE,
    EmulationError,
    EmulationModel,
    Firmware,
    compile_plan,
    descriptor,
    read_descriptors,
)
from fang.lang import System
from fang.verification import questions

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SENSOR_NODE = _load("sensor_node_for_simavr_tests", ROOT / "examples" / "sensor_node" / "sensor_node.py")


def _elaborate(system):
    from fang.elaborate import elaborate

    result = elaborate(system, project_id="PRJ-EXAMPLES")
    assert result.ok, [d.message for d in result.diagnostics]
    return result


def _question(snapshot, attribute):
    return next(q for q in questions(snapshot) if q.label.endswith(f".{attribute}"))


def _recorded_for(question, engine: str | None):
    """The question as if elaboration had recorded `engine`, or none."""
    data = {key: value for key, value in question.data.items() if key != "engine"}
    if engine is not None:
        data["engine"] = engine
    return dataclasses.replace(question, data=data)


# -- engines ------------------------------------------------------------------


def test_every_platform_descriptor_names_its_emulator():
    assert descriptor("fang:stm32f401re").engine == "renode"
    assert descriptor("fang:stm32f401re").is_platform
    assert descriptor("renode:Sensors.HS3001").engine == "renode"
    assert not descriptor("renode:Sensors.HS3001").is_platform


def test_a_descriptor_id_shipped_twice_is_refused(tmp_path):
    for package in ("one", "two"):
        folder = tmp_path / package
        folder.mkdir()
        (folder / "part.json").write_text(
            json.dumps({"id": "fang:same", "kind": "simavr_platform", "engine": "simavr"})
        )
    with pytest.raises(EmulationError, match="two emulation model descriptors") as refused:
        read_descriptors([tmp_path / "one", tmp_path / "two"])
    assert refused.value.code == "model"


def test_a_question_records_its_platforms_emulator():
    result = _elaborate(SENSOR_NODE.SensorNode)
    recorded = {q.data.get("engine") for q in questions(result.snapshot) if q.method == "emulation"}
    assert recorded == {"renode"}


def test_a_board_with_no_shipped_platform_model_records_no_emulator():
    class Unshipped(SENSOR_NODE.SensorNode):
        def __init__(self, **overrides):
            System.__init__(self, **overrides)
            self.mcu.add_trait(EmulationModel(source="fang:no-such-part"))
            self.mcu.add_trait(Firmware("firmware/elf/sensor_node.elf", target="stm32f401re"))

    result = _elaborate(Unshipped)
    assert "engine" not in _question(result.snapshot, "startup").data


def test_a_question_recorded_for_another_emulator_is_refused():
    result = _elaborate(SENSOR_NODE.SensorNode)
    forged = _recorded_for(_question(result.snapshot, "startup"), "simavr")
    with pytest.raises(EmulationError) as refused:
        compile_plan(result.snapshot, forged, traits=result.traits)
    assert refused.value.code == "target"
    assert "recorded for simavr" in str(refused.value) and "runs on renode" in str(refused.value)


def test_each_tool_covers_only_its_own_emulators_questions():
    result = _elaborate(SENSOR_NODE.SensorNode)
    question = _question(result.snapshot, "startup")
    assert RENODE.covers(question)
    assert not RENODE.covers(_recorded_for(question, "simavr"))
    # Recorded before emulators were: every such question was Renode's.
    assert RENODE.covers(_recorded_for(question, None))


def test_recording_the_emulator_leaves_the_job_as_it_was():
    """The job names its tool, which routing chose by the recorded emulator,
    so the emulator is not counted again in what the job asks: a Renode
    job prepared before questions recorded their emulator keeps its hash."""
    result = _elaborate(SENSOR_NODE.SensorNode)
    question = _question(result.snapshot, "startup")
    now = RENODE.prepare(result.snapshot, question, traits=result.traits)
    before = RENODE.prepare(result.snapshot, _recorded_for(question, None), traits=result.traits)
    assert now.hash == before.hash
    assert "engine" not in now.manifest()["asks"]


# -- the ATtiny84A ------------------------------------------------------------


def test_the_attiny84a_descriptor_is_simavrs_and_states_how_the_part_ships():
    """Its compare outputs are the datasheet's (DS40002269A, figure 1-1 and
    section 10.2): the pins simavr 1.6 got wrong."""
    model = descriptor("fang:attiny84a")
    assert (model.engine, model.kind, model.document["mcu"]) == ("simavr", "simavr_platform", "attiny84")
    assert model.document["compare_outputs"] == {"OC0A": "PB2", "OC0B": "PA7", "OC1A": "PA6", "OC1B": "PA5"}
    pins = model.document["pins"]
    assert pins["PB2"] == {"port": "B", "index": 2} and pins["PA5"] == {"port": "A", "index": 5}
    assert model.document["clock"]["fuses"] == {"low": "0x62", "high": "0xDF", "extended": "0xFF"}
    assert model.document["peripherals"] == {}


# -- a board to plan against --------------------------------------------------

from fang.diagnostics import FangError  # noqa: E402
from fang.emulation import (  # noqa: E402
    CLOCKED_PLAN_SCHEMA,
    PLAN_SCHEMA,
    Count,
    Emulates,
    Rises,
    plan_from_dict,
)
from fang.interfaces import Pin, PinMap, PowerIn, PowerOut  # noqa: E402
from fang.lang import Ohm, Parameter, Part, Signal, UnitLiteral, V, ms, require, s  # noqa: E402
from fang.parts import LED, Resistor  # noqa: E402
from fang.rationale import Requires  # noqa: E402

count = UnitLiteral("1")


class Tiny84(Part):
    """An ATtiny84A reduced to the pins a one-LED board uses."""

    designator_prefix = "U"
    power = PowerIn(voltage=5 * V)
    led = Signal()
    VCC = Pin("VCC", role="power", number="1")
    PB2 = Pin("PB2", role="data", number="5")
    GND = Pin("GND", role="ground", number="14")
    pinmap = PinMap({"power.vcc": "VCC", "power.gnd": "GND", "led.line": "PB2"})


class Supply(Part):
    designator_prefix = "J"
    dc = PowerOut(voltage=5 * V)
    VCC = Pin("VCC", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")
    pinmap = PinMap({"dc.vcc": "VCC", "dc.gnd": "GND"})


def blinker(*, bound=None, asked=None, firmware="fixtures/simavr/firmware/elf/blink.elf"):
    """A one-LED ATtiny84A board, its firmware bound with `bound` fuses and
    its question stating `asked`; None leaves either unstated."""

    class Blinker(System):
        blinks = Requires("The firmware blinks the LED", validation="emulation")
        rises = Parameter("", description="LED rises in the first 100 ms")
        run = Emulates(
            "blinks", run_until=100 * ms, fuses=asked,
            measures={"rises": Count(Rises("mcu.led"))}, abstracted=("series",),
        )
        supply = Supply(package="PinHeader_1x02_P2.54mm")
        mcu = Tiny84(package="SOIC-14")
        series = Resistor(resistance=680 * Ohm, package="R_0603")
        lamp = LED(package="LED_1206")

        def __init__(self, **overrides):
            super().__init__(**overrides)
            self.mcu.add_trait(EmulationModel(source="fang:attiny84a"))
            self.mcu.add_trait(Firmware(firmware, target="attiny84a", fuses=bound))

        def architecture(self):
            self.supply.dc >> self.mcu.power
            self.mcu.led >> self.series.p1
            self.series.p2 >> self.lamp.p1
            self.lamp.p2 >> self.supply.dc.gnd

        def constraints(self):
            require(self.rises >= 1 * count)

    return Blinker


def _planned(**fuses):
    result = _elaborate(blinker(**fuses))
    return compile_plan(result.snapshot, _question(result.snapshot, "run"), traits=result.traits)


# -- fuses ------------------------------------------------------------------------


def test_fuses_are_stated_as_factory_or_by_byte():
    assert Firmware("f.elf", target="attiny84a", fuses="factory").fuses == "factory"
    assert Firmware("f.elf", target="attiny84a", fuses={"low": 0xE2}).fuses == {"low": "0xE2"}
    # The canonical form reads back as itself.
    assert Firmware("f.elf", target="attiny84a", fuses={"low": "0xE2"}).fuses == {"low": "0xE2"}
    # Unstated is absent from the binding's record, not a value in it.
    assert "fuses" not in Firmware("f.elf", target="attiny84a").as_dict()


@pytest.mark.parametrize(
    "fuses",
    [{"lock": 0xFF}, {"low": 0x100}, {"low": -1}, {"low": True}, {}, "as shipped", 0x62],
)
def test_a_fuse_no_avr_part_has_or_no_byte_is_refused_where_declared(fuses):
    with pytest.raises(FangError) as refused:
        Firmware("f.elf", target="attiny84a", fuses=fuses)
    assert refused.value.diagnostic.code == "SIM-0017"
    with pytest.raises(FangError) as refused:
        Emulates("blinks", run_until=100 * ms, fuses=fuses, measures={})
    assert refused.value.diagnostic.code == "SIM-0017"


def test_a_question_records_the_fuses_it_states():
    result = _elaborate(blinker(bound={"low": 0xE2}, asked="factory"))
    question = _question(result.snapshot, "run")
    assert question.data["scenario"]["fuses"] == "factory"
    assert question.data["engine"] == "simavr"


# -- the clock --------------------------------------------------------------------


def test_a_part_as_it_ships_runs_at_an_eighth_of_its_oscillator():
    plan = _planned(bound="factory")
    assert plan.clock["oscillator_hz"] == 8_000_000 and plan.clock["prescaler"] == 8
    assert plan.core_clock_hz == 1_000_000
    assert plan.clock["fuses"] == {"low": "0x62", "high": "0xDF", "extended": "0xFF"}
    assert plan.clock["source"] == "factory"
    assert any("starts at 1000000 Hz" in a and "factory fuses" in a for a in plan.assumptions)
    assert any("14 CK + 64 ms after reset" in a for a in plan.assumptions)


def test_the_fuses_the_board_is_programmed_with_set_the_clock():
    plan = _planned(bound={"low": 0xE2})
    assert (plan.clock["prescaler"], plan.core_clock_hz) == (1, 8_000_000)
    assert plan.clock["fuses"]["low"] == "0xE2" and plan.clock["source"] == "binding"


def test_the_questions_fuses_win_over_the_bindings():
    plan = _planned(bound={"low": 0xE2}, asked="factory")
    assert (plan.clock["prescaler"], plan.clock["source"]) == (8, "factory")
    plan = _planned(bound="factory", asked={"low": 0xE2})
    assert (plan.clock["prescaler"], plan.clock["source"]) == (1, "question")


def test_the_internal_128_khz_oscillator_is_modelled():
    plan = _planned(bound={"low": 0xE4})
    assert plan.clock["oscillator_hz"] == 128_000 and plan.core_clock_hz == 128_000


def test_unstated_fuses_refuse_the_plan():
    with pytest.raises(EmulationError) as refused:
        _planned()
    assert refused.value.code == "clock"
    assert "system.mcu" in str(refused.value) and "'factory'" in str(refused.value)


@pytest.mark.parametrize(
    "fuses, says",
    [
        # CKSEL 0000: an external clock.
        ({"low": 0xE0}, "clock-select bits (CKSEL) are 0x0"),
        # WDTON programmed: the watchdog always on.
        ({"high": 0xCF}, "the high fuse of system.mcu is 0xCF: bits 0x10"),
        # CKOUT programmed: the clock on PB2.
        ({"low": 0xA2}, "the low fuse of system.mcu is 0xA2: bits 0x40"),
        # SUT 11, which the part reserves.
        ({"low": 0xF2}, "start-up bits (SUT) are 0x3"),
    ],
)
def test_a_fuse_value_the_model_does_not_cover_is_refused(fuses, says):
    with pytest.raises(EmulationError) as refused:
        _planned(bound=fuses)
    assert refused.value.code == "clock" and says in str(refused.value)


# -- the plan's schema --------------------------------------------------------------


def test_a_plan_with_no_clock_is_written_as_before():
    result = _elaborate(SENSOR_NODE.SensorNode)
    plan = compile_plan(result.snapshot, _question(result.snapshot, "startup"), traits=result.traits)
    assert plan.schema == PLAN_SCHEMA == "fang.emulation/v2"
    assert plan.clock is None and "clock" not in plan.as_dict()


def test_a_clocked_plan_is_v3_and_reads_back_with_its_hash():
    plan = _planned(bound={"low": 0xE2})
    assert plan.schema == CLOCKED_PLAN_SCHEMA == "fang.emulation/v3"
    written = plan.as_dict()
    back = plan_from_dict(written)
    assert back.hash == plan.hash == written["plan"] and back.clock == plan.clock


def test_a_plans_schema_and_its_clock_must_agree():
    written = _planned(bound={"low": 0xE2}).as_dict()
    with pytest.raises(ValueError, match="carries a clock"):
        plan_from_dict({**written, "schema": PLAN_SCHEMA})
    without = {key: value for key, value in written.items() if key != "clock"}
    with pytest.raises(ValueError, match="lacks a clock"):
        plan_from_dict(without)


# -- the fraction of a window ---------------------------------------------------

from decimal import Decimal  # noqa: E402

from fang.emulation import Duty, EmulationPlan, Event, RunRecord, measure  # noqa: E402

MS = 1_000_000


@pytest.mark.parametrize(
    "level, within",
    [
        (2, (0 * ms, 10 * ms)),
        (True, (0 * ms, 10 * ms)),
        (0, None),
        (0, (10 * ms, 5 * ms)),
        (0, (1 * V, 2 * V)),
        (0, (0 * ms,)),
    ],
)
def test_a_fraction_of_a_window_is_refused_where_it_cannot_be_measured(level, within):
    with pytest.raises(FangError) as refused:
        Duty("mcu.led", level=level, within=within)
    assert refused.value.diagnostic.code in ("SIM-0003", "UNIT-0001")


def test_a_fraction_of_a_window_is_planned_on_its_pin():
    class Measured(blinker(bound={"low": 0xE2})):
        lit = Parameter("", description="the LED's duty at level 0 in the first 10 ms")
        run = Emulates(
            "blinks", run_until=100 * ms,
            measures={"lit": Duty("mcu.led", level=0, within=(0 * ms, 10 * ms))}, abstracted=("series",),
        )

        def constraints(self):
            require(self.lit >= 0 * count)

    result = _elaborate(Measured)
    plan = compile_plan(result.snapshot, _question(result.snapshot, "run"), traits=result.traits)
    spec = plan.measures["lit"]
    assert (spec["kind"], spec["level"], spec["within_ns"]) == ("duty", 0, [0, 10 * MS])
    assert [(o.kind, o.emulator, o.index) for o in plan.observations] == [("gpio", "B", 2)]
    assert spec["entity"] == plan.observations[0].entity


def _duty_plan(level, start_ms, end_ms):
    return EmulationPlan(
        question="VER-q", requirement="REQ-r", snapshot="", machine="board",
        platform="fang:attiny84a", platform_file="", recorder_port="", target="mcu",
        firmware_path="f.elf", firmware_target="attiny84a", core_clock_hz=8_000_000, seed=0,
        run_until_ns=20 * MS,
        measures={"d": {"kind": "duty", "entity": "led", "level": level,
                        "within_ns": [start_ms * MS, end_ms * MS]}},
    )


def _pin(*changes, end_ms=20, warnings=()):
    """A completed run: `changes` are (ms, level) with level None a release."""
    events = [Event(0, 0, "", "run.start", {})]
    for t, level in changes:
        if level is None:
            events.append(Event(len(events), t * MS, "led", "gpio.release", {}))
        else:
            events.append(Event(len(events), t * MS, "led", "gpio.edge", {"level": level}))
    for t, source, text in warnings:
        events.append(Event(len(events), t * MS, source, "model.warning", {"text": text}))
    events.sort(key=lambda e: e.t_ns)
    events = [Event(n, e.t_ns, e.source, e.type, e.payload) for n, e in enumerate(events)]
    events.append(Event(len(events), end_ms * MS, "", "run.end", {"reason": "completed"}))
    return RunRecord(tuple(events), "completed")


def _duty(level, start_ms, end_ms, record):
    (value,) = measure(_duty_plan(level, start_ms, end_ms), record)
    return value


def test_a_fraction_over_a_fully_observed_window():
    record = _pin((0, 1), (2, 0), (5, 1))
    low, high = _duty(0, 0, 10, record).quantity, _duty(1, 0, 10, record).quantity
    assert low.kind == high.kind == "scalar"
    assert (low.value, high.value) == (Decimal("0.3"), Decimal("0.7"))


def test_released_time_is_at_neither_level():
    record = _pin((0, 0), (6, None))
    assert _duty(0, 0, 10, record).quantity.value == Decimal("0.6")
    assert _duty(1, 0, 10, record).quantity.value == 0


def test_a_window_partly_before_the_first_level_is_an_interval():
    record = _pin((2, 0), (6, 1))
    value = _duty(0, 0, 10, record).quantity
    assert value.kind == "range"
    assert value.interval() == (Decimal("0.4"), Decimal("0.6"))


def test_a_window_past_the_runs_end_is_an_interval():
    record = _pin((0, 0), end_ms=8)
    assert _duty(0, 0, 10, record).quantity.interval() == (Decimal("0.8"), Decimal("1"))
    assert _duty(1, 0, 10, _pin(end_ms=20)).quantity.interval() == (0, 1)


def test_a_platform_warning_withdraws_every_measure():
    record = _pin((0, 0), warnings=[(3, "mcu", "OSCCAL written 0x10")])
    (value,) = measure(_duty_plan(0, 0, 10), record)
    assert value.quantity is None
    assert value.reason == "withdrawn: mcu warned: OSCCAL written 0x10"


# -- the lowering -------------------------------------------------------------------

import hashlib  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import subprocess  # noqa: E402

from fang.simavr import LoweringError, bundle, configuration, flash_image  # noqa: E402
from fang.simavr.lowering import CONFIG, FLASH, MANIFEST, RUNNER  # noqa: E402

QUIET_ORBIT_ELF = ROOT / "examples" / "quiet_orbit" / "firmware" / "elf" / "quiet-orbit-qo-r1.elf"
FIXTURE_ELF = ROOT / "tests" / "fixtures" / "simavr" / "firmware" / "elf"
SENSOR_NODE_ELF = ROOT / "examples" / "sensor_node" / "firmware" / "elf" / "sensor_node.elf"


def _segment_at(elf: bytes, index: int, address: int) -> bytes:
    """The ELF with program header `index`'s physical address moved."""
    (phoff,) = struct.unpack_from("<I", elf, 28)
    (phentsize,) = struct.unpack_from("<H", elf, 42)
    patched = bytearray(elf)
    struct.pack_into("<I", patched, phoff + index * phentsize + 12, address)
    return bytes(patched)


def test_the_flash_image_is_what_a_programmer_writes():
    """The same bytes `avr-objcopy -O binary -R .eeprom` gives, which the
    spike checked for this ELF; compared again where avr-objcopy is here."""
    elf = QUIET_ORBIT_ELF.read_bytes()
    image = flash_image(elf, 8192)
    assert len(image) == 246
    assert hashlib.sha256(image).hexdigest() == "b97357738d2b0c4a77992dd14a911efa6c6ba0d1270c940946a865a137ea5acd"
    if shutil.which("avr-objcopy"):
        made = subprocess.run(
            ["avr-objcopy", "-O", "binary", "-R", ".eeprom", "-R", ".fuse", "-R", ".lock",
             "-R", ".signature", str(QUIET_ORBIT_ELF), "/dev/stdout"],
            capture_output=True, check=True,
        ).stdout
        assert made == image


def test_initialized_data_is_flashed_where_startup_copies_it_from():
    """blink's table is in .data: run from RAM at 0x800060, held in flash
    right after .text, at 0x76, where the startup code copies it from."""
    image = flash_image((FIXTURE_ELF / "blink.elf").read_bytes(), 8192)
    assert len(image) == 0x7A and image[0x76:0x7A] == struct.pack("<HH", 2000, 2000)


@pytest.mark.parametrize(
    "firmware, says",
    [
        (lambda: b"not an elf at all" * 4, "not an ELF"),
        (lambda: SENSOR_NODE_ELF.read_bytes(), "not AVR"),
        (lambda: _segment_at((FIXTURE_ELF / "blink.elf").read_bytes(), 1, 0x810000), "EEPROM image"),
        (lambda: _segment_at((FIXTURE_ELF / "blink.elf").read_bytes(), 1, 0x800060), "into RAM"),
    ],
)
def test_firmware_that_is_not_an_avr_flash_image_is_refused(firmware, says):
    with pytest.raises(LoweringError, match=says):
        flash_image(firmware(), 8192)


def test_firmware_larger_than_the_parts_flash_is_refused():
    with pytest.raises(LoweringError, match="past the part's 100 bytes"):
        flash_image(QUIET_ORBIT_ELF.read_bytes(), 100)


def test_the_runner_reads_only_what_the_lowering_writes():
    plan = _planned(bound={"low": 0xE2})
    lines = configuration(plan, descriptor("fang:attiny84a").document).splitlines()
    assert lines[:10] == [
        "fang-simavr-run 1",
        "mcu attiny84",
        "oscillator_hz 8000000",
        "prescaler 1",
        "prescaler_register 0x46",
        "seed 0",
        "run_until_ns 100000000",
        "flash flash.bin",
        "events events.jsonl",
        f"target {plan.target}",
    ]
    assert lines[10:] == [
        f"pin {plan.observations[0].entity} B 2",
        "watch OSCCAL 0x51 0xFF write",
        "watch PRR 0x20 0x07 set",
    ]


@pytest.mark.parametrize("field, value", [("target", 'CMP-1" x'), ("target", "CMP 1"), ("target", "")])
def test_an_identifier_outside_the_validated_form_is_refused(field, value):
    plan = dataclasses.replace(_planned(bound={"low": 0xE2}), **{field: value})
    with pytest.raises(LoweringError, match="not an identifier the lowering will write"):
        configuration(plan, descriptor("fang:attiny84a").document)


def test_the_bundle_is_a_function_of_the_plan_and_the_firmware():
    plan = _planned(bound={"low": 0xE2})
    firmware = (FIXTURE_ELF / "blink.elf").read_bytes()
    first, second = bundle(plan, firmware), bundle(plan, firmware)
    assert first == second
    assert set(first) == {"plan.json", CONFIG, RUNNER, "firmware.elf", FLASH, MANIFEST}
    manifest = json.loads(first[MANIFEST])
    assert manifest["engine"] == {"name": "simavr", "versions": ["1.8"]}
    assert set(manifest["files"]) == set(first) - {MANIFEST}
    assert manifest["files"][RUNNER] == "sha256:" + hashlib.sha256(first[RUNNER]).hexdigest()


# -- the runner and the backend -----------------------------------------------------

from fang.emulation import SIMAVR  # noqa: E402
from fang.simavr import SimavrBackend, SimavrUnavailable  # noqa: E402

needs_simavr = pytest.mark.skipif(
    shutil.which("simavr") is None or shutil.which(os.environ.get("CC") or "cc") is None,
    reason="simavr, or a C compiler to build the runner against it, is not installed",
)


def _fake_simavr(tmp_path, *, version="v1.8", headers=True, library=True) -> SimavrBackend:
    """A stand-in installation laid out as `make install` lays simavr out."""
    prefix = tmp_path / "simavr"
    (prefix / "bin").mkdir(parents=True)
    executable = prefix / "bin" / "simavr"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    if headers:
        (prefix / "include" / "simavr").mkdir(parents=True)
        (prefix / "include" / "simavr" / "sim_avr.h").write_text("/* stand-in */\n")
        (prefix / "include" / "simavr" / "sim_core_config.h").write_text(
            f'#define CONFIG_SIMAVR_VERSION "{version}"\n'
        )
    if library:
        (prefix / "lib").mkdir()
        (prefix / "lib" / "libsimavr.a").write_bytes(b"!<arch>\n")
    return SimavrBackend(executable=str(executable))


def test_simavr_is_found_by_its_executable_and_read_beside_it(tmp_path):
    backend = _fake_simavr(tmp_path)
    assert backend.available()
    assert backend.check() == ("1.8", hashlib.sha256(b"!<arch>\n").hexdigest()[:12])


def test_simavr_1_6_is_refused_for_the_fault_it_has(tmp_path):
    with pytest.raises(SimavrUnavailable) as refused:
        _fake_simavr(tmp_path, version="1.6").check()
    assert "simavr 1.6 is installed" in str(refused.value)
    assert "checked against 1.8" in str(refused.value)
    assert "compare outputs" in str(refused.value) and "PB2, PA7, PA6 and PA5" in str(refused.value)


def test_an_unchecked_simavr_version_is_refused_by_its_version(tmp_path):
    with pytest.raises(SimavrUnavailable, match="simavr 2.0 is installed, and the lowering was checked against 1.8"):
        _fake_simavr(tmp_path, version="v2.0").check()


@pytest.mark.parametrize("missing, says", [("headers", "without its headers"), ("library", "without its library")])
def test_an_installation_the_runner_cannot_be_built_against_is_refused(tmp_path, missing, says):
    with pytest.raises(SimavrUnavailable, match=says):
        _fake_simavr(tmp_path, **{missing: False}).check()


def test_a_missing_simavr_reports_unsupported():
    backend = SimavrBackend(executable="simavr-that-is-not-installed")
    assert not backend.available()
    with pytest.raises(SimavrUnavailable, match="not installed"):
        backend.run({}, timeout=5)


def _job(bound, firmware, *, asked=None, run_until=100 * ms):
    class Board(blinker(bound=bound, asked=asked, firmware=f"fixtures/simavr/firmware/elf/{firmware}.elf")):
        run = Emulates(
            "blinks", run_until=run_until, fuses=asked,
            measures={"rises": Count(Rises("mcu.led"))}, abstracted=("series",),
        )

    result = _elaborate(Board)
    question = _question(result.snapshot, "run")
    return question, SIMAVR.prepare(result.snapshot, question, traits=result.traits)


def _events(raw):
    return [json.loads(line) for line in raw.outputs["events.jsonl"].decode().splitlines()]


@needs_simavr
def test_the_runner_builds_warning_free_and_refuses_a_line_it_does_not_know(tmp_path):
    backend = SimavrBackend()
    installation = backend.installation()
    source = tmp_path / RUNNER
    source.write_bytes((ROOT / "fang" / "simavr" / "runner" / RUNNER).read_bytes())
    compiler, _ = backend.compiler()
    link = (
        ["-L", str(installation.library.parent), "-lsimavr", f"-Wl,-rpath,{installation.library.parent}"]
        if installation.shared else [str(installation.library), "-lelf"]
    )
    subprocess.run(
        [compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-I", str(installation.include),
         "-o", "fang-runner", RUNNER, *link, "-lm"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    (tmp_path / "run.cfg").write_text("fang-simavr-run 1\nmcu attiny84\nexec /bin/sh\n")
    refused = subprocess.run(["./fang-runner", "run.cfg"], cwd=tmp_path, capture_output=True, text=True)
    assert refused.returncode == 2 and "not a line of the fixed set" in refused.stderr


@needs_simavr
def test_a_pin_is_recorded_only_while_it_is_driven(tmp_path):
    """Timer 0 drives OC0A from the start; PB2 becomes an output at about
    0.5 ms and an input again at about 1 ms."""
    _, job = _job({"low": 0xE2}, "pins", run_until=5 * ms)
    events = _events(SIMAVR.run(job, workspace=tmp_path))
    pin = [e for e in events if e["type"] in ("gpio.edge", "gpio.release")]
    assert 490_000 < pin[0]["t_ns"] < 520_000 and pin[0]["type"] == "gpio.edge"
    assert pin[-1]["type"] == "gpio.release" and 990_000 < pin[-1]["t_ns"] < 1_020_000
    assert sum(1 for e in pin if e["type"] == "gpio.edge") > 30


@needs_simavr
@pytest.mark.parametrize("firmware, ratio", [("prescaler", 8), ("late", 1)])
def test_the_firmwares_own_prescaler_change_is_modelled(tmp_path, firmware, ratio):
    """From the factory fuses' 1 MHz, a change written in time takes the edges
    eight times as fast; one written ten cycles late changes nothing."""
    _, job = _job("factory", firmware, run_until=200 * ms)
    events = _events(SIMAVR.run(job, workspace=tmp_path))

    def rises(start_ms, end_ms):
        return sum(
            1 for e in events
            if e["type"] == "gpio.edge" and e["payload"]["level"] == 1 and start_ms * MS <= e["t_ns"] < end_ms * MS
        )

    before, after = rises(0, 100), rises(110, 200)
    assert round(after / before * 100 / 90) == ratio
    changes = [e for e in events if e["type"] == "clock.change"]
    assert [c["payload"] for c in changes] == ([{"prescaler": 1}] if ratio == 8 else [])


@needs_simavr
def test_a_calibration_write_withdraws_the_run(tmp_path):
    question, job = _job({"low": 0xE2}, "osccal")
    raw = SIMAVR.run(job, workspace=tmp_path)
    warnings = [e["payload"]["text"] for e in _events(raw) if e["type"] == "model.warning"]
    assert warnings == ["OSCCAL written 0x01: the model does not model it"]
    (rises,) = SIMAVR.read(job, raw)
    assert rises.quantity is None and "OSCCAL written 0x01" in rises.reason


@needs_simavr
def test_a_modelled_power_reduction_bit_does_not_warn(tmp_path):
    _, job = _job({"low": 0xE2}, "prtim1")
    raw = SIMAVR.run(job, workspace=tmp_path)
    assert not [e for e in _events(raw) if e["type"] == "model.warning"]
    (rises,) = SIMAVR.read(job, raw)
    assert rises.quantity.value == 50


@needs_simavr
def test_a_core_that_halts_ends_a_run_that_has_not_completed(tmp_path):
    _, job = _job({"low": 0xE2}, "halt")
    raw = SIMAVR.run(job, workspace=tmp_path)
    assert raw.outputs["outcome"] == "halted"
    assert _events(raw)[-1]["payload"] == {"reason": "halted"}
    (rises,) = SIMAVR.read(job, raw)
    assert rises.quantity is None and rises.reason == "the run did not complete"


def seeded_serial(seed: int) -> str:
    """The serial number the runner gives the core: splitmix64 of the seed."""
    mask = (1 << 64) - 1
    z, out = (seed + 0x9E3779B97F4A7C15) & mask, []
    for _ in range(9):
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & mask
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & mask
        z ^= z >> 31
        out.append(f"{z & 0xFF:02x}")
    return " ".join(out)


@needs_simavr
def test_ten_runs_give_one_record_and_the_seeds_serial_number(tmp_path):
    _, job = _job({"low": 0xE2}, "blink")
    records, logs = set(), set()
    for n in range(10):
        raw = SIMAVR.run(job, workspace=tmp_path / f"run-{n}")
        records.add(bytes(raw.outputs["events.jsonl"]))
        logs.add((tmp_path / f"run-{n}" / "simavr.log").read_text())
    assert len(records) == 1 and len(logs) == 1
    assert f"fang-runner: serial {seeded_serial(0)} from seed 0" in logs.pop()


@needs_simavr
def test_a_hung_run_is_ended_whole_and_keeps_its_partial_events():
    _, job = _job({"low": 0xE2}, "blink", run_until=3600 * s)
    files = {name: (c.encode() if isinstance(c, str) else c) for name, c in job.files.items()}
    run = SimavrBackend().run(files, timeout=3)
    assert run.outcome == "timeout" and run.exit_status is None
    if shutil.which("pgrep"):
        survivors = subprocess.run(["pgrep", "-f", "fang-runner run.cfg"], capture_output=True, text=True).stdout
        assert survivors.strip() == ""
    assert run.events.count(b"gpio.edge") > 10 and b"run.end" not in run.events


@needs_simavr
def test_a_runner_that_does_not_build_reports_unsupported(tmp_path, monkeypatch):
    monkeypatch.setenv("CC", shutil.which("false"))
    _, job = _job({"low": 0xE2}, "blink")
    from fang.verification import ToolUnavailable

    with pytest.raises(ToolUnavailable, match="the runner did not build against simavr"):
        SIMAVR.run(job, workspace=tmp_path)
    assert not list(tmp_path.iterdir()), "a run that could not be made writes nothing"


def test_a_missing_compiler_reports_unsupported(monkeypatch):
    monkeypatch.setenv("CC", "no-such-compiler")
    with pytest.raises(SimavrUnavailable, match=r"no C compiler \(no-such-compiler\)"):
        SimavrBackend().compiler()


def test_an_avr_question_is_never_run_on_renode():
    """It routes to simavr whatever is installed, and is unsupported there,
    naming simavr, where simavr is missing."""
    from fang.verification import route

    result = _elaborate(blinker(bound={"low": 0xE2}))
    question = _question(result.snapshot, "run")
    routed = route(result.snapshot, question)
    assert routed.tool == "simavr"
    assert not RENODE.covers(question) and SIMAVR.covers(question)


def test_a_missing_simavr_leaves_an_avr_question_unsupported(tmp_path, monkeypatch):
    from fang.checks import DEFAULT_CHECKS
    from fang.graph import KernelGraph
    from fang.verification import answer

    monkeypatch.setattr(SIMAVR, "backend", SimavrBackend(executable="simavr-that-is-not-installed"))
    result = _elaborate(blinker(bound={"low": 0xE2}))
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    question = _question(graph.head, "run")
    outcome = answer(graph, question, traits=result.traits, workspace=tmp_path)
    assert outcome.status == "unsupported" and "simavr" in outcome.message
    assert graph.head.entities[question.id].result == "UNKNOWN"


# -- recorded runs, measured without simavr ----------------------------------------
#
# Recorded by the runner on simavr 1.8 from the fixture firmware on the
# one-LED board, and committed under tests/fixtures/simavr/events/.

from fang.emulation import run_record  # noqa: E402

EVENTS = ROOT / "tests" / "fixtures" / "simavr" / "events"


def _recorded_plan(firmware: str, run_until):
    class Board(blinker(bound={"low": 0xE2}, firmware=f"fixtures/simavr/firmware/elf/{firmware}.elf")):
        lit = Parameter("", description="PB2 low between 10 ms and 90 ms")
        early = Parameter("", description="PB2 high in the first millisecond")
        run = Emulates(
            "blinks", run_until=run_until,
            measures={
                "rises": Count(Rises("mcu.led")),
                "lit": Duty("mcu.led", level=0, within=(10 * ms, 90 * ms)),
                "early": Duty("mcu.led", level=1, within=(0 * ms, 1 * ms)),
            },
            abstracted=("series",),
        )

        def constraints(self):
            require(self.rises >= 1 * count)
            require(self.lit >= 0 * count)
            require(self.early >= 0 * count)

    result = _elaborate(Board)
    return compile_plan(result.snapshot, _question(result.snapshot, "run"), traits=result.traits)


def _measured(firmware: str, run_until, outcome="completed") -> dict:
    record = run_record((EVENTS / f"{firmware}.jsonl").read_bytes(), outcome)
    return {m.name: m for m in measure(_recorded_plan(firmware, run_until), record)}


def test_a_recorded_blink_is_counted_and_its_duty_taken():
    found = _measured("blink", 100 * ms)
    assert found["rises"].quantity.value == 50
    lit = found["lit"].quantity
    assert lit.kind == "scalar" and Decimal("0.49") < lit.value < Decimal("0.51")
    # PB2 is first driven at 7.125 us: before it, nothing was observed.
    low, high = found["early"].quantity.interval()
    assert high - low == Decimal("0.007125")


def test_a_recorded_release_counts_at_neither_level():
    """PB2 is driven from 0.502375 ms to 1.0025 ms of the run and never again."""
    record = run_record((EVENTS / "pins.jsonl").read_bytes(), "completed")
    plan = _recorded_plan("pins", 5 * ms)
    spec = dict(plan.measures["early"], within_ns=[0, 2 * MS])
    (value,) = measure(dataclasses.replace(plan, measures={"window": spec}), record)
    low, high = value.quantity.interval()
    assert high - low == Decimal("502375") / Decimal(2 * MS)
    assert high < Decimal("0.5")


def test_a_recorded_halt_measures_nothing():
    found = _measured("halt", 100 * ms, outcome="halted")
    assert {m.reason for m in found.values()} == {"the run did not complete"}


def test_a_recorded_calibration_write_withdraws_every_measure():
    found = _measured("osccal", 10 * ms)
    assert all(m.quantity is None for m in found.values())
    assert all("OSCCAL written 0x01" in m.reason for m in found.values())


def test_a_partly_observed_fraction_decides_only_what_it_can():
    """[0.4, 0.6]: at most 0.7 is decided, at least 0.5 is not."""
    from fang.constraints import Literal, Truth, ge, le
    from fang.units import Quantity

    value = Literal(quantity=_duty(0, 0, 10, _pin((2, 0), (6, 1))).quantity)
    bound = lambda x: Literal(quantity=Quantity.scalar(Decimal(x), "1"))  # noqa: E731
    assert le(value, bound("0.7")).evaluate(lambda *_: None) is Truth.TRUE
    assert ge(value, bound("0.5")).evaluate(lambda *_: None) is Truth.UNDECIDED


def test_every_expected_warning_is_a_gap_of_every_run():
    """RFC 12 section 12.13: an expected warning stands for something the
    model does not model, so its gap is on every run, warned of or not."""
    from fang.emulation import descriptors

    for model in descriptors().values():
        assert {w["gap"] for w in model.expected_warnings} <= set(model.not_modelled), model.id


# -- the command --------------------------------------------------------------------

QUIET_ORBIT = ROOT / "examples" / "quiet_orbit" / "quiet_orbit.py"


def _cli(*argv):
    from fang.cli import main

    return main(list(argv))


def test_emulate_writes_an_attiny_bundle_without_running_anything(tmp_path, capsys):
    assert _cli("emulate", str(QUIET_ORBIT), "--bundle-only", "-o", str(tmp_path)) == 0
    printed = capsys.readouterr().out
    assert "simavr 1.8" not in printed and "plan sha256:" in printed
    for question in ("orbit", "as_shipped"):
        written = {p.name for p in (tmp_path / question).iterdir()}
        assert written == {"plan.json", "run.cfg", "fang_runner.c", "firmware.elf", "flash.bin", "manifest.json"}


@needs_simavr
def test_emulate_names_the_emulator_each_question_ran_on(capsys):
    assert _cli("emulate", str(QUIET_ORBIT)) == 0
    printed = capsys.readouterr().out
    assert "simavr 1.8 (build" in printed and "renode" not in printed
    assert "pwm_rises = 489" in printed and "shipped_pwm_rises = 60" in printed
