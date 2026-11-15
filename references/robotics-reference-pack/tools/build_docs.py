#!/usr/bin/env python3
"""Regenerate the human-readable component library, datasheet index and the
single-file ALL_IN_ONE.md from components.json and the project files.

Run from the pack root:  python3 tools/build_docs.py
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
lib = json.loads((ROOT / "components" / "components.json").read_text())

PROJECT_NAMES = {
    "swerve3": "3-pod swerve",
    "ftc_decode": "FTC DECODE robot",
    "arm4dof": "4-DOF VR arm",
    "diffdrive": "Stepper diff drive",
    "tripod": "Tripod vehicle",
}


def md_escape(s: str) -> str:
    return str(s).replace("|", "\\|")


# ---------- component_library.md ----------
out = ["# Component library", "",
       "Generated from `components.json` by `tools/build_docs.py`. Edit the JSON, then rebuild.", "",
       "## Usage matrix", "",
       "| Component | " + " | ".join(PROJECT_NAMES.values()) + " |",
       "|---|" + "---|" * len(PROJECT_NAMES)]
for c in lib["components"]:
    row = [md_escape(c["name"])] + ["x" if p in c["used_in"] else "" for p in PROJECT_NAMES]
    out.append("| " + " | ".join(row) + " |")
out.append("")
for c in lib["components"]:
    out += [f"## {c['name']}", "",
            f"- **id:** `{c['id']}`  ",
            f"- **category:** {c['category']}  ",
            f"- **manufacturer:** {c['manufacturer']}  ",
            f"- **used in:** {', '.join(PROJECT_NAMES[p] for p in c['used_in'])}", "",
            "| Spec | Value |", "|---|---|"]
    for k, v in c["key_specs"].items():
        out.append(f"| {k.replace('_', ' ')} | {md_escape(v)} |")
    out.append("")
    if c.get("interfaces"):
        out.append("**Interfaces:** " + "; ".join(c["interfaces"]))
        out.append("")
    if c.get("gotchas"):
        out.append("**Gotchas:**")
        out += [f"- {g}" for g in c["gotchas"]]
        out.append("")
    if c.get("datasheets"):
        out.append("**Datasheets:**")
        for d in c["datasheets"]:
            flag = "" if d["verified_url"] else " *(link pattern not verified)*"
            out.append(f"- [{d['label']}]({d['url']}){flag}")
        out.append("")
(ROOT / "components" / "component_library.md").write_text("\n".join(out))

# ---------- datasheet_index.md ----------
idx = ["# Datasheet index", "",
       "Every link in the pack, grouped by component. To download them all locally run:", "",
       "```", "python3 datasheets/fetch_datasheets.py", "```", "",
       "Files land in `datasheets/<component_id>/`. Links marked *unverified* follow the vendor's usual URL pattern but were not confirmed when the pack was built; if one fails, search the vendor site for the part number.", "",
       "| Component | Document | Link | Status |", "|---|---|---|---|"]
for c in lib["components"]:
    for d in c.get("datasheets", []):
        idx.append(f"| `{c['id']}` | {md_escape(d['label'])} | {d['url']} | {'verified' if d['verified_url'] else 'unverified'} |")
idx += ["", "## Other references", ""]
idx += [f"- [{r['label']}]({r['url']})" for r in lib.get("references", [])]
(ROOT / "datasheets" / "datasheet_index.md").write_text("\n".join(idx) + "\n")

# ---------- ALL_IN_ONE.md ----------
parts = [ROOT / "README.md", ROOT / "00_design_patterns.md"]
parts += sorted((ROOT / "projects").glob("*.md"))
parts += [ROOT / "components" / "component_library.md", ROOT / "datasheets" / "datasheet_index.md"]
blob = ["<!-- Single-file bundle of the robotics reference pack for agents with one-document context. -->", ""]
for p in parts:
    blob += [f"\n\n<!-- ===== {p.relative_to(ROOT)} ===== -->\n", p.read_text()]
(ROOT / "ALL_IN_ONE.md").write_text("\n".join(blob))
print("built component_library.md, datasheet_index.md, ALL_IN_ONE.md")
