import dataclasses
import inspect
import json
import typing
from pathlib import Path

import pytest

from backend.contracts.parts import load_library
from backend.contracts.results import ToolResult
from backend.contracts.runner import StageRunner
from backend.contracts.spec import Layout, ProjectSpec
from backend.contracts.tools import ToolBox
from backend.runtime.stages import run_stages
from backend.tools.fakes import FIXTURE_RUN, fake_toolbox
from backend.tools.toolbox import real_toolbox

TOOLS = typing.get_type_hints(ToolBox)


def params(fn) -> list[str]:
    return [p for p in inspect.signature(fn).parameters if p != "self"]


@pytest.mark.parametrize("name", list(TOOLS))
def test_real_tool_matches_its_protocol(name):
    """Checked by signature, not by calling: real tools may compile, build CAD or use the network."""
    tool = getattr(real_toolbox(), name)
    assert params(tool) == params(TOOLS[name].__call__), name
    assert typing.get_type_hints(tool)["return"] is ToolResult, name


def test_stage_runner_stub_matches_its_protocol():
    assert params(run_stages)[:4] == params(StageRunner.__call__)


def test_fake_toolbox_succeeds_and_writes_only_inside_out_dir(tmp_path):
    box = fake_toolbox()
    fixture = ProjectSpec.model_validate_json((FIXTURE_RUN / "spec.json").read_text())
    spec = fixture.model_copy(update={"rev": fixture.rev + 1})  # as after an edit
    lib = load_library()
    layout = Layout.model_validate_json(
        (FIXTURE_RUN / "cad" / "layout.json").read_text()
    )
    calls = {
        "validate_spec": lambda f: f(spec, lib),
        "compute_layout": lambda f: f(spec, lib, tmp_path / "cad"),
        "build_enclosure": lambda f: f(spec, layout, lib, tmp_path / "cad"),
        "build_custom_model": lambda f: f(spec, layout, lib, tmp_path / "cad"),
        "check_enclosure": lambda f: f(spec, layout, lib, tmp_path / "cad", "generic"),
        "build_assembly": lambda f: f(spec, layout, lib, tmp_path / "cad"),
        "write_firmware_project": lambda f: f(
            spec, lib, "// main", tmp_path / "firmware"
        ),
        "lint_firmware": lambda f: f(tmp_path / "firmware"),
        "compile_firmware": lambda f: f(tmp_path / "firmware"),
        "build_wiring": lambda f: f(spec, lib, tmp_path),
        "build_simulation": lambda f: f(
            spec, lib, tmp_path / "firmware", tmp_path / "sim"
        ),
        "run_simulation": lambda f: f(tmp_path / "sim", 5000, "P2D_READY"),
        "price_bom": lambda f: f(spec, lib, None, tmp_path),
        "cross_checks": lambda f: f(tmp_path, spec, lib),
        "preprocess_input": lambda f: f([Path("sketch.png")], tmp_path / "input"),
    }
    assert set(calls) == {f.name for f in dataclasses.fields(ToolBox)}
    for name, call in calls.items():
        result = call(getattr(box, name))
        assert result.ok, name
        for path in result.artifacts.values():
            assert Path(path).is_absolute() and Path(path).is_file(), (name, path)
            assert Path(path).is_relative_to(tmp_path.resolve()), (name, path)
    for rel in ("wiring.json", "bom.json", "cad/manifest.json"):
        assert json.loads((tmp_path / rel).read_text())["spec_rev"] == spec.rev, rel


def test_stubs_return_skipped_tool_results():
    stub = real_toolbox().preprocess_input([], Path("unused"))
    assert isinstance(stub, ToolResult) and stub.skipped and not stub.ok
    assert not ToolResult(ok=False).skipped
