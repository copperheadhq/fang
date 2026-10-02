"""Touchstone models, read in-tree, and the closed-form answers they give.

Spec: "A Touchstone Model Is Data" and "Verification Tools Sit Behind One
Protocol".

A part may carry its network parameters -- a vendor's file, or a network
analyser's -- as a `Touchstone` trait. A question over it is answered by
reading the file and composing the matching parts it names in closed form:
the load the file describes, each part a series or a shunt element by how the
graph connects it, with the value the graph holds. Nothing is simulated and
nothing is extrapolated: a frequency outside the file's range is refused,
naming the range.

The arithmetic is complex numbers in the standard library: the option line
(`# GHZ S MA R 50`), the RI, MA and DB formats, renormalization to the
question's reference, and a ladder of series and shunt elements. Binary floats
never cross into the graph: every result is quantized to six significant
figures before it becomes a `Decimal`, so the last bits of a logarithm cannot
differ between platforms in a committed output.
"""

from __future__ import annotations

import cmath
import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .diagnostics import SIM_OUTSIDE_MODEL_RANGE, SIM_UNRESOLVED_SURFACE
from .runtime import Status
from .serialization import canonical_dumps
from .simulation import (
    Level,
    SimulationError,
    bundle_paths,
    model_path,
    si_magnitude,
    spice_nodes,
    spice_number,
)
from .units import Quantity
from .values import Value
from .verification import (
    Job,
    Measurement,
    NotRunnable,
    Question,
    RawRun,
    model_confidence,
)

#: Frequency units an option line may name, to hertz. Decimal, so a file's
#: last point scaled to hertz is the frequency a question names, not the
#: binary float nearest it: 2.01 * 1e9 is 2009999999.9999998.
FREQUENCY_UNITS = {
    "HZ": Decimal(1), "KHZ": Decimal("1E3"), "MHZ": Decimal("1E6"), "GHZ": Decimal("1E9"),
}
FORMATS = ("RI", "MA", "DB")


class TouchstoneError(ValueError):
    """A file that is not a Touchstone file this reader reads."""


@dataclass(frozen=True)
class Network:
    """An N-port's scattering parameters, as the file gives them.

    Frequencies are hertz, ascending, and decimal: they are scaled and
    compared exactly, so a question at a point the file names is at that
    point. Each point holds the N x N parameters in the file's order,
    normalized to the file's reference resistance.
    """

    ports: int
    frequencies: tuple[Decimal, ...]
    parameters: tuple[tuple[complex, ...], ...]
    reference: float

    @property
    def span(self) -> tuple[Decimal, Decimal]:
        return self.frequencies[0], self.frequencies[-1]

    def reflection(self, frequency: Decimal | float | int) -> complex:
        """S11 at a frequency, interpolated linearly in real and imaginary
        parts between the two points around it; refused outside the file."""
        frequency = _decimal_hertz(frequency)
        low, high = self.span
        if not low <= frequency <= high:
            raise TouchstoneError(
                f"{_hertz(frequency)} lies outside the file's range, "
                f"{_hertz(low)} to {_hertz(high)}"
            )
        points = self.frequencies
        for index in range(len(points)):
            if points[index] == frequency:
                return self.parameters[index][0]
            if points[index] > frequency:
                f0, f1 = points[index - 1], points[index]
                s0, s1 = self.parameters[index - 1][0], self.parameters[index][0]
                weight = float((frequency - f0) / (f1 - f0))
                return s0 + (s1 - s0) * weight
        return self.parameters[-1][0]

    def impedance(self, reflection: complex) -> complex:
        """The impedance a reflection coefficient describes, against the
        file's reference."""
        if reflection == 1:
            raise TouchstoneError("the model is an open circuit there; it has no impedance")
        return self.reference * (1 + reflection) / (1 - reflection)


def _decimal_hertz(value: Decimal | float | int) -> Decimal:
    """A frequency as a Decimal; a float through its shortest decimal form,
    never its binary expansion."""
    if isinstance(value, Decimal):
        return value
    return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)


def _hertz(value: Decimal) -> str:
    """A frequency for a person to read, at six significant figures."""
    giga = Decimal("1E9")
    if value >= giga:
        return f"{format(float(value / giga), '.6g')} GHz"
    return f"{format(float(value), '.6g')} Hz"


def read_touchstone(text: str, *, ports: int) -> Network:
    """Read a version 1 Touchstone file of S-parameters.

    The option line's frequency unit, format and reference resistance are
    honoured, with the format's defaults (GHz, MA, 50 Ohm) where it is silent.
    A file of Y, Z, H or G parameters is refused rather than read as S.
    """
    unit, form, reference = "GHZ", "MA", 50.0
    numbers: list[str] = []
    for raw in text.splitlines():
        line = raw.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("#"):
            tokens = line[1:].upper().split()
            index = 0
            while index < len(tokens):
                token = tokens[index]
                if token in FREQUENCY_UNITS:
                    unit = token
                elif token in FORMATS:
                    form = token
                elif token == "R" and index + 1 < len(tokens):
                    reference = float(tokens[index + 1])
                    index += 1
                elif token in ("Y", "Z", "H", "G"):
                    raise TouchstoneError(f"the file holds {token} parameters; only S is read")
                elif token != "S":
                    raise TouchstoneError(f"the option line names {token!r}, which is not read")
                index += 1
            continue
        if line.startswith("["):
            raise TouchstoneError("version 2 keywords are not read")
        # Kept as written: a frequency is read as a Decimal and a parameter as
        # a float, each from the text the file holds.
        tokens = line.split()
        try:
            for token in tokens:
                float(token)
        except ValueError:
            raise TouchstoneError(f"{line!r} is not a line of numbers") from None
        numbers.extend(tokens)

    width = 1 + 2 * ports * ports
    if not numbers or len(numbers) % width:
        raise TouchstoneError(
            f"the data does not divide into points of {width} numbers for {ports} port(s)"
        )
    frequencies: list[Decimal] = []
    parameters: list[tuple[complex, ...]] = []
    for start in range(0, len(numbers), width):
        point = numbers[start:start + width]
        try:
            frequency = Decimal(point[0]) * FREQUENCY_UNITS[unit]
        except ArithmeticError:
            raise TouchstoneError(f"{point[0]!r} is not a frequency") from None
        if not frequency.is_finite():
            raise TouchstoneError(f"{point[0]!r} is not a frequency")
        frequencies.append(frequency)
        values = []
        for first, second in zip(map(float, point[1::2]), map(float, point[2::2])):
            if form == "RI":
                values.append(complex(first, second))
            elif form == "MA":
                values.append(cmath.rect(first, math.radians(second)))
            else:
                values.append(cmath.rect(10 ** (first / 20), math.radians(second)))
        parameters.append(tuple(values))
    if any(b <= a for a, b in zip(frequencies, frequencies[1:])):
        raise TouchstoneError("the file's frequencies do not ascend")
    return Network(ports, tuple(frequencies), tuple(parameters), reference)


def ports_of(source: str, declared: Sequence[str] = ()) -> int:
    """How many ports a file describes: its `.sNp` extension says."""
    found = re.search(r"\.s(\d+)p$", source, re.IGNORECASE)
    if found:
        return int(found.group(1))
    if declared:
        return len(declared)
    raise TouchstoneError(f"{source} is not named .sNp and the trait names no ports")


@dataclass(frozen=True)
class Element:
    """One matching part: a series or a shunt L, C or R, in SI units."""

    name: str
    kind: str          # "series" or "shunt"
    device: str        # "L", "C" or "R"
    value: float

    def impedance(self, omega: float) -> complex:
        if self.device == "L":
            return complex(0, omega * self.value)
        if self.device == "C":
            return 1 / complex(0, omega * self.value)
        return complex(self.value, 0)


def one_port(load: complex, elements: Sequence[Element], omega: float) -> complex:
    """The impedance seen at the port through the elements, which are named
    in order from the port toward the load."""
    impedance = load
    for element in reversed(elements):
        own = element.impedance(omega)
        if element.kind == "series":
            impedance = impedance + own
        else:
            impedance = 1 / (1 / impedance + 1 / own)
    return impedance


def return_loss(impedance: complex, reference: float) -> float:
    """-20 log10 |Gamma| against a reference resistance, in dB."""
    gamma = abs((impedance - reference) / (impedance + reference))
    return math.inf if gamma == 0 else -20 * math.log10(gamma)


def quantize(value: float, figures: int = 6) -> Decimal:
    """A float as a Decimal at six significant figures: the boundary binary
    floats do not cross."""
    if math.isinf(value):
        return Decimal("Infinity") if value > 0 else Decimal("-Infinity")
    return Decimal(format(value, f".{figures}g"))


# --------------------------------------------------------------------------
# The tool
# --------------------------------------------------------------------------

EVALUATION = "evaluation.json"
RESULT = "result.json"

#: The parameter each matching part's value is read from, by designator prefix.
_DEVICES = {"L": "inductance", "C": "capacitance", "R": "resistance"}


@dataclass
class TouchstoneTool:
    """Return loss from a Touchstone model, at the equation level.

    Preparation writes the evaluation -- the model file and its digest, the
    frequency, the reference, and each matching part with its kind and the
    value the graph holds -- and refuses a frequency outside the file. The run
    reads the declared model file and composes the ladder; it is the reader
    itself, so it is always available and its version is fang's.
    """

    name: str = "touchstone"
    level: Level = Level.EQUATION

    def covers(self, question: Question) -> bool:
        measures = question.measures
        return question.method == "analysis" and bool(measures) and all(
            entry.record.get("kind") == "return_loss" for entry in measures
        )

    def available(self) -> bool:
        return True

    def version(self) -> str:
        from . import __version__

        return f"fang {__version__}"

    def prepare(self, snapshot, question: Question, *, traits=None) -> Job:
        from .netlist import compile_netlist
        from .traits import TraitRegistry

        traits = traits or TraitRegistry()
        netlist = compile_netlist(snapshot, traits=traits)
        nodes = spice_nodes(snapshot, netlist)
        designator_of = {c.entity_id: c.designator for c in netlist.components}
        pins_of: dict[str, list[str]] = {}
        for entity in snapshot.entities.values():
            if entity.kind == "pin":
                pins_of.setdefault(entity.owner, []).append(entity.vendor_name)
        parts = {
            part["name"]: part["component"]
            for part in question.data.get("evaluation", {}).get("parts", ())
        }

        measures, read, confidences = [], [], []
        assumptions, gaps = [], set()
        for entry in question.measures:
            measure = entry.measure
            surface = question.surface(measure.surface)
            if not surface or "signal" not in surface:
                raise NotRunnable(
                    f"{question.label} names {measure.surface!r}, which resolves to no pins",
                    code=SIM_UNRESOLVED_SURFACE,
                )
            carrier = surface["signal"]["component"]
            label = _label(snapshot, carrier)
            trait = traits.get(carrier, "touchstone")
            if trait is None:
                raise NotRunnable(f"{label} carries no Touchstone model to read")
            try:
                path, location = model_path(snapshot.entities[carrier], trait.source)
                data = location.read_bytes()
                count = ports_of(trait.source, trait.ports)
                network = read_touchstone(data.decode("utf-8", errors="replace"), ports=count)
            except (SimulationError, TouchstoneError) as exc:
                raise NotRunnable(f"{question.label}: {exc}") from None
            if trait.ports and surface["signal"]["pin"] != trait.ports[0]:
                raise NotRunnable(
                    f"{measure.surface} lands on {surface['signal']['pin']}, which is not "
                    f"port 1 of {label}'s model ({trait.ports[0]})"
                )

            frequency = si_magnitude(measure.at)
            low, high = network.span
            if not low <= frequency <= high:
                raise NotRunnable(
                    f"{question.label} asks for {measure.at}, outside {path}'s range, "
                    f"{_hertz(low)} to {_hertz(high)}; nothing is extrapolated",
                    code=SIM_OUTSIDE_MODEL_RANGE,
                )

            elements = []
            for position, name in enumerate(measure.through):
                elements.append(
                    self._element(snapshot, position, name, parts, designator_of, nodes, pins_of)
                )
            digest = "sha256:" + hashlib.sha256(data).hexdigest()
            read.append((len(measures), path, digest, str(location)))
            confidences.append(model_confidence(trait.provenance))
            measures.append(
                {
                    "name": entry.name,
                    "parameter": entry.parameter,
                    "unit": entry.unit,
                    "model": path,
                    "ports": count,
                    "at": spice_number(frequency),
                    "reference": spice_number(si_magnitude(measure.reference)),
                    "elements": elements,
                }
            )
            assumptions.append(
                f"{entry.name}: the port is driven against {measure.reference}, through "
                + (", ".join(measure.through) or "no matching part")
                + f", into {label}'s model at {measure.at}"
            )
            if count > 1:
                assumptions.append(
                    f"{label}'s ports after the first are terminated in the file's reference"
                )
            gaps.add(f"{label}'s model is interpolated linearly between the file's points")
            if measure.through:
                gaps.add(
                    "each matching part is an ideal element: no parasitic resistance, "
                    "no self-resonance, and no trace or pad between them"
                )

        # Two carriers in different folders may name their files by one
        # relative path; each measure reads its own file, under its own name.
        inputs, sources = {}, {}
        named = bundle_paths((path, digest) for _, path, digest, _ in read)
        for index, path, digest, location in read:
            measures[index]["model"] = named[(path, digest)]
            inputs[named[(path, digest)]] = digest
            sources[named[(path, digest)]] = location

        return Job.single(
            self.name,
            question,
            snapshot.hash,
            EVALUATION,
            canonical_dumps({"measures": measures}) + "\n",
            assumptions=tuple(assumptions),
            coverage_gaps=tuple(sorted(gaps)),
            inputs=inputs,
            sources=sources,
            confidence=min(confidences, default=Decimal(1)),
        )

    @staticmethod
    def _element(snapshot, position, name, parts, designator_of, nodes, pins_of) -> dict:
        component = parts.get(name)
        if component is None:
            raise NotRunnable(f"the matching part {name!r} was not resolved at elaboration")
        entity = snapshot.entities[component]
        label = _label(snapshot, component)
        device = entity.extensions.get("designator_prefix")
        if device not in _DEVICES:
            raise NotRunnable(f"{label} is not an inductor, a capacitor or a resistor")
        terminals = [nodes[(designator_of[component], pin)] for pin in sorted(pins_of.get(component, ()))]
        if len(terminals) != 2:
            raise NotRunnable(f"{label} has {len(terminals)} terminals; a matching element has two")
        element = {
            "position": position,
            "name": name,
            "component": component,
            "kind": "shunt" if "0" in terminals else "series",
            "device": device,
        }
        value = entity.parameters.get(_DEVICES[device])
        if isinstance(value, Value) and value.known and value.quantity is not None:
            try:
                element["value"] = spice_number(si_magnitude(value.quantity))
                return element
            except SimulationError as exc:
                element["reason"] = f"{label}'s {_DEVICES[device]}: {exc}"
                return element
        element["reason"] = f"{label}'s {_DEVICES[device]} is unknown"
        return element

    def run(self, job: Job, *, workspace: Path) -> RawRun:
        """Read the declared model file and compose the ladder, per measure."""
        version = self.version()
        try:
            evaluation = json.loads(job.input)
            results = {}
            for measure in evaluation["measures"]:
                chain = sorted(measure["elements"], key=lambda element: element["position"])
                unknown = [element["reason"] for element in chain if "value" not in element]
                if unknown:
                    results[measure["name"]] = {"reason": "; ".join(unknown)}
                    continue
                data = Path(job.sources[measure["model"]]).read_bytes()
                if "sha256:" + hashlib.sha256(data).hexdigest() != job.inputs[measure["model"]]:
                    raise TouchstoneError(f"{measure['model']} changed after the job was prepared")
                network = read_touchstone(data.decode("utf-8", errors="replace"), ports=measure["ports"])
                frequency = Decimal(measure["at"])
                load = network.impedance(network.reflection(frequency))
                ladder = [
                    Element(e["name"], e["kind"], e["device"], float(Decimal(e["value"])))
                    for e in chain
                ]
                seen = one_port(load, ladder, 2 * math.pi * float(frequency))
                loss = quantize(return_loss(seen, float(Decimal(measure["reference"]))))
                results[measure["name"]] = {"value": loss}
        except (KeyError, OSError, ValueError) as exc:
            return RawRun(self.name, version, 1, status=Status.FAILED, message=str(exc))
        return RawRun(self.name, version, 0, outputs={RESULT: canonical_dumps(results)})

    def read(self, job: Job, raw: RawRun) -> tuple[Measurement, ...]:
        results = json.loads(raw.outputs[RESULT]) if raw.status is Status.SUCCEEDED else {}
        out = []
        for entry in job.question.measures:
            found = results.get(entry.name, {})
            quantity, reason = None, None
            if raw.status is not Status.SUCCEEDED:
                reason = f"the evaluation did not complete: {raw.message}"
            elif "value" in found:
                quantity, _ = Quantity.scalar(Decimal(found["value"]), "dB").converted_to(entry.unit)
            else:
                reason = found.get("reason", "the evaluation does not report it")
            out.append(
                Measurement(
                    entry.name, entry.parameter, quantity, self.name, raw.version,
                    job.hash, job.confidence, reason,
                )
            )
        return tuple(out)


def _label(snapshot, entity_id: str) -> str:
    entity = snapshot.entities.get(entity_id)
    return str(entity.identity.path or entity_id) if entity is not None else entity_id


#: The Touchstone reader, a built-in tool at the equation level.
TOUCHSTONE = TouchstoneTool()
