"""real_toolbox(): the real tools. Each one starts as a stub returning not_implemented and becomes real
when its task merges; nothing here changes."""

from backend.cad.assembly import build_assembly
from backend.contracts.tools import ToolBox
from backend.runtime.wiring import build_wiring
from backend.tools.build_enclosure import build_enclosure
from backend.tools.check_enclosure import check_enclosure
from backend.tools.cross_checks import cross_checks
from backend.tools.firmware import (
    compile_firmware,
    lint_firmware,
    write_firmware_project,
)
from backend.tools.layout import compute_layout
from backend.tools.preprocess_input import preprocess_input
from backend.tools.pricing import price_bom
from backend.tools.simulation import build_simulation, run_simulation
from backend.tools.validate_spec import validate_spec


def real_toolbox() -> ToolBox:
    return ToolBox(
        validate_spec=validate_spec,
        compute_layout=compute_layout,
        build_enclosure=build_enclosure,
        check_enclosure=check_enclosure,
        build_assembly=build_assembly,
        write_firmware_project=write_firmware_project,
        lint_firmware=lint_firmware,
        compile_firmware=compile_firmware,
        build_wiring=build_wiring,
        build_simulation=build_simulation,
        run_simulation=run_simulation,
        price_bom=price_bom,
        cross_checks=cross_checks,
        preprocess_input=preprocess_input,
    )
