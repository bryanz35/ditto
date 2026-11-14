import shutil
from pathlib import Path

import pytest

from backend.contracts.parts import PartLibrary, load_library
from backend.contracts.spec import Layout, ProjectSpec

ROOT = Path(__file__).resolve().parents[3]
CAD = ROOT / "fixtures" / "runs" / "plant_monitor" / "cad"


@pytest.fixture
def lib() -> PartLibrary:
    return load_library()


@pytest.fixture
def spec() -> ProjectSpec:
    return ProjectSpec.model_validate_json(
        (ROOT / "fixtures" / "specs" / "plant_monitor.json").read_text()
    )


@pytest.fixture
def layout() -> Layout:
    return Layout.model_validate_json((CAD / "layout.json").read_text())


@pytest.fixture
def cad_dir(tmp_path) -> Path:
    for name in ("base.stl", "lid.stl"):
        shutil.copy(CAD / name, tmp_path / name)
    return tmp_path
