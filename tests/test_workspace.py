"""Spec: Workspace Persistence; The Workspace Layout."""

import json

import pytest

from fang.elaborate import elaborate
from fang.importing import MappingTable
from fang.serialization import canonical_record_stream
from fang.workspace import DIRECTORIES, Manifest, Workspace, find_workspace
from fang.diagnostics import FangError
from examples.divider import Divider

PROJECT = "PRJ-WS"


@pytest.fixture
def built(tmp_path):
    result = elaborate(Divider, project_id=PROJECT)
    assert result.ok
    workspace = Workspace(tmp_path)
    manifest = workspace.write_snapshot(result.snapshot)
    return result, workspace, manifest


def test_the_workspace_creates_its_directories(tmp_path):
    workspace = Workspace(tmp_path).create()
    assert workspace.exists
    for name in DIRECTORIES:
        assert (workspace.dir / name).is_dir()


def test_the_workspace_round_trips_a_design(built):
    result, workspace, _ = built
    records = workspace.read_records()
    assert len(records) == len(result.snapshot.entities)
    assert {r["id"] for r in records} == set(result.snapshot.entities)


def test_the_design_file_is_the_canonical_record_stream(built):
    result, workspace, _ = built
    assert workspace.design_path.read_bytes() == canonical_record_stream(
        result.snapshot.records()
    )


def test_the_manifest_records_what_produced_the_state(built):
    result, workspace, manifest = built
    assert manifest.snapshot == result.snapshot.hash
    assert manifest.schema_version == result.snapshot.schema_version
    assert manifest.compiler_version == result.snapshot.compiler_version
    assert manifest.project_id == PROJECT
    assert manifest.entity_count == len(result.snapshot.entities)

    reread = workspace.read_manifest()
    assert reread == manifest


def test_a_manifest_with_an_unimplemented_major_version_is_refused(built):
    _, workspace, _ = built
    payload = json.loads(workspace.manifest_path.read_text())
    payload["schema_version"] = "9.0"
    workspace.manifest_path.write_text(json.dumps(payload))
    with pytest.raises(FangError):
        workspace.read_manifest()


def test_deleting_the_cache_loses_no_engineering_fact(built, tmp_path):
    result, workspace, manifest = built
    workspace.create()
    (workspace.cache / "derived.txt").write_text("regenerate me")

    workspace.clear_cache()
    assert workspace.cache.is_dir()
    assert list(workspace.cache.iterdir()) == []

    # Everything canonical survives, and a rebuild lands on the same snapshot.
    assert workspace.read_manifest() == manifest
    rebuilt = elaborate(Divider, project_id=PROJECT)
    assert rebuilt.snapshot.hash == manifest.snapshot


def test_the_mapping_table_persists_between_runs(tmp_path):
    workspace = Workspace(tmp_path).create()
    table = MappingTable()
    table.record("R1", "CMP-abc")
    workspace.write_mapping(table)

    reloaded = workspace.read_mapping()
    assert reloaded.canonical("R1") == "CMP-abc"


def test_an_absent_mapping_reads_as_empty(tmp_path):
    workspace = Workspace(tmp_path).create()
    assert len(workspace.read_mapping()) == 0


def test_the_plan_and_import_report_are_persisted(tmp_path):
    result = elaborate(Divider, project_id=PROJECT)
    workspace = Workspace(tmp_path).create()
    workspace.write_plan(result.plan)

    from fang.importing import ImportReport

    report = ImportReport("divider.net")
    report.note("weird", "divider.net:3")
    workspace.write_import_report(report)

    assert json.loads((workspace.dir / "plan.json").read_text())["calls"] == []
    stored = json.loads((workspace.dir / "import-report.json").read_text())
    assert stored["unrepresented"][0]["construct"] == "weird"


def test_finding_a_workspace_walks_upward(tmp_path):
    Workspace(tmp_path).create()
    nested = tmp_path / "src" / "boards"
    nested.mkdir(parents=True)
    found = find_workspace(nested)
    assert found is not None
    assert found.root == tmp_path


def test_finding_a_workspace_returns_none_when_there_is_none(tmp_path):
    assert find_workspace(tmp_path) is None
