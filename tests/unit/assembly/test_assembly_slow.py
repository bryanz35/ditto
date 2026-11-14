"""Real pipeline build of the plant-monitor assembly, loaded by three.js's GLTFLoader (make test-slow)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.cad.assembly import build_assembly
from backend.contracts.spec import Layout
from backend.tools.build_enclosure import build_enclosure
from backend.tools.layout import compute_layout
from tests.unit.assembly.conftest import ROOT

pytestmark = pytest.mark.slow
THREE = ROOT / "frontend" / "node_modules" / "three"


@pytest.mark.skipif(
    not shutil.which("node") or not THREE.exists(),
    reason="needs node and frontend/node_modules (make setup)",
)
def test_plant_monitor_real_pipeline_loads_in_gltfloader(spec, lib, tmp_path):
    layout = Layout.model_validate(compute_layout(spec, lib, tmp_path).data["layout"])
    assert build_enclosure(spec, layout, lib, tmp_path).ok
    result = build_assembly(spec, layout, lib, tmp_path)
    assert result.ok, result.errors
    out = subprocess.run(
        [
            "node",
            str(Path(__file__).with_name("gltf_load.mjs")),
            result.artifacts["assembly_glb"],
            str(THREE),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    meshes = {m["name"]: m["userData"] for m in json.loads(out.stdout)}
    refs = {p.ref for p in layout.placements}
    assert sorted(meshes) == sorted(refs | {"base", "lid"})
    insts = {p.ref: p for p in [spec.mcu, *spec.parts]}
    for ref in refs:
        part = lib.get(insts[ref].part_id)
        assert meshes[ref]["unmeasured"] is (part.dims_source != "measured")
