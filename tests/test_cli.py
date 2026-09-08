"""Spec: The Command Surface."""

import json
from pathlib import Path

import pytest

from fang.cli import EXIT_FAILED, EXIT_OK, load_system, main
from fang.workspace import Workspace

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
DIVIDER = str(EXAMPLES / "divider" / "divider.py")
SENSOR = str(EXAMPLES / "sensor_board" / "sensor_board.py")


def test_init_creates_a_workspace(tmp_path):
    assert main(["init", "-C", str(tmp_path)]) == EXIT_OK
    assert Workspace(tmp_path).exists


def test_building_a_program_writes_the_workspace(tmp_path, capsys):
    code = main(["build", DIVIDER, "--project", "PRJ-CLI", "-C", str(tmp_path)])
    assert code == EXIT_OK

    workspace = Workspace(tmp_path)
    assert workspace.design_path.exists()
    manifest = workspace.read_manifest()
    assert manifest.project_id == "PRJ-CLI"
    assert manifest.entity_count > 0
    assert manifest.snapshot in capsys.readouterr().out


def test_graph_summarizes_the_kernel_graph(capsys):
    assert main(["graph", SENSOR, "--project", "PRJ-CLI"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "component" in output
    assert "pin" in output
    assert "total" in output


def test_netlist_lists_components_and_nets(capsys):
    assert main(["netlist", SENSOR, "--project", "PRJ-CLI"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "U1" in output and "R1" in output
    assert "Net-(" in output


def test_export_writes_a_kicad_netlist(tmp_path, capsys):
    target = tmp_path / "board.net"
    code = main(["export", SENSOR, "--project", "PRJ-CLI", "-o", str(target)])
    assert code == EXIT_OK
    assert target.read_text().startswith('(export "version" "E"')


def test_export_writes_to_stdout_without_an_output_path(capsys):
    assert main(["export", DIVIDER, "--project", "PRJ-CLI"]) == EXIT_OK
    assert capsys.readouterr().out.startswith('(export "version" "E"')


def test_check_reports_and_exits_zero_when_nothing_fails(capsys):
    assert main(["check", SENSOR, "--project", "PRJ-CLI"]) == EXIT_OK
    assert "checks" in capsys.readouterr().out


def test_a_failing_check_exits_non_zero(tmp_path, capsys):
    program = tmp_path / "bad.py"
    program.write_text(
        "from fang.lang import System, V, kOhm, require\n"
        "from fang.parts import Resistor\n"
        "\n"
        "class Bad(System):\n"
        "    r = Resistor(resistance=10 * kOhm)\n"
        "\n"
        "    def constraints(self):\n"
        "        require(self.r.resistance <= 1 * kOhm)\n"
    )
    assert main(["check", str(program), "--project", "PRJ-CLI"]) == EXIT_FAILED
    assert "FAIL" in capsys.readouterr().err


def test_a_failed_elaboration_reports_its_diagnostics(tmp_path, capsys):
    program = tmp_path / "broken.py"
    program.write_text(
        "from fang.lang import Ground, Mechanical, Part, System\n"
        "\n"
        "class P(Part):\n"
        "    g = Ground()\n"
        "    m = Mechanical()\n"
        "\n"
        "class Broken(System):\n"
        "    p = P()\n"
        "\n"
        "    def architecture(self):\n"
        "        self.p.g >> self.p.m\n"
    )
    assert main(["build", str(program), "--project", "PRJ-CLI", "-C", str(tmp_path)]) == EXIT_FAILED

    errors = capsys.readouterr().err
    assert "ELAB-0005" in errors
    assert "broken.py:" in errors
    # No partial workspace is left behind.
    assert not Workspace(tmp_path).design_path.exists()


def test_a_program_error_is_a_diagnostic_not_a_traceback(tmp_path, capsys):
    program = tmp_path / "wrong_units.py"
    program.write_text(
        "from fang.lang import System, uF\n"
        "from fang.parts import Resistor\n"
        "\n"
        "class Wrong(System):\n"
        "    r = Resistor(resistance=10 * uF)\n"
    )
    assert main(["graph", str(program), "--project", "PRJ-CLI"]) == EXIT_FAILED
    assert "UNIT-0001" in capsys.readouterr().err


def test_a_file_with_no_system_is_refused(tmp_path, capsys):
    program = tmp_path / "empty.py"
    program.write_text("x = 1\n")
    assert main(["graph", str(program), "--project", "PRJ-CLI"]) == EXIT_FAILED


def test_a_file_with_several_systems_asks_which_one(tmp_path):
    program = tmp_path / "two.py"
    program.write_text(
        "from fang.lang import System\n"
        "class A(System):\n    pass\n"
        "class B(System):\n    pass\n"
    )
    with pytest.raises(SystemExit, match="more than one system"):
        load_system(program)
    assert load_system(program, "B").__name__ == "B"


def test_diff_reports_no_change_after_a_build(tmp_path, capsys):
    assert main(["build", DIVIDER, "--project", "PRJ-CLI", "-C", str(tmp_path)]) == EXIT_OK
    capsys.readouterr()
    assert main(["diff", DIVIDER, "--project", "PRJ-CLI", "-C", str(tmp_path)]) == EXIT_OK
    assert "no change" in capsys.readouterr().out


def test_diff_without_a_workspace_says_so(tmp_path, capsys):
    assert main(["diff", DIVIDER, "--project", "PRJ-CLI", "-C", str(tmp_path)]) == EXIT_FAILED
    assert "no workspace" in capsys.readouterr().err


def test_the_build_runs_the_programs_tool_plan(tmp_path, capsys):
    program = tmp_path / "planned.py"
    program.write_text(
        "from fang.lang import System, kOhm, tools\n"
        "from fang.parts import Resistor\n"
        "\n"
        "class Planned(System):\n"
        "    a = Resistor(resistance=10 * kOhm, package='R_0603')\n"
        "    b = Resistor(resistance=10 * kOhm, package='R_0603')\n"
        "\n"
        "    def architecture(self):\n"
        "        self.a.p2 >> self.b.p1\n"
        "        n = tools.netlist()\n"
        "        r = tools.check(profile='jlcpcb-2layer')\n"
        "        tools.export(netlist=n, format='kicad', require=r.passed)\n"
    )
    assert main(["build", str(program), "--project", "PRJ-CLI", "-C", str(tmp_path)]) == EXIT_OK
    output = capsys.readouterr().out
    assert "netlist" in output and "export" in output
    assert "succeeded" in output
    assert (Workspace(tmp_path).cache / "design.net").exists()


def test_sim_compiles_a_plan_and_writes_a_deck(tmp_path, capsys):
    deck = tmp_path / "deck.cir"
    code = main(
        [
            "sim", DIVIDER, "--project", "PRJ-CLI",
            "--analysis", "transient", "--stop", "10ms", "--probe", "V(1)",
            "-o", str(deck), "-C", str(tmp_path),
        ]
    )
    text = deck.read_text()
    assert ".tran" in text and ".print transient V(1)" in text
    assert text.strip().endswith(".end")
    # ngspice is absent in most environments; the plan still compiles, and the
    # command refuses to invent a result.
    captured = capsys.readouterr()
    if code != EXIT_OK:
        assert "no result is fabricated" in captured.err


def test_sim_reports_a_rejected_plan_rather_than_running_it(tmp_path, capsys):
    program = tmp_path / "unmodelled.py"
    program.write_text(
        "from fang.lang import Part, System\n"
        "\n"
        "class Chip(Part):\n"
        "    designator_prefix = 'U'\n"
        "\n"
        "class Board(System):\n"
        "    u = Chip()\n"
    )
    assert main(["sim", str(program), "--project", "PRJ-CLI", "-C", str(tmp_path)]) == EXIT_FAILED
    assert "plan was rejected" in capsys.readouterr().err


def test_sim_prints_the_coverage_the_run_does_not_provide(tmp_path, capsys):
    main(["sim", DIVIDER, "--project", "PRJ-CLI", "-C", str(tmp_path)])
    assert "coverage gap" in capsys.readouterr().out
