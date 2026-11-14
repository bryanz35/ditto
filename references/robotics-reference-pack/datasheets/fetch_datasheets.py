#!/usr/bin/env python3
"""Download every datasheet listed in ../components/components.json into this folder.

Usage (from the pack root or this folder):
    python3 datasheets/fetch_datasheets.py            # download all
    python3 datasheets/fetch_datasheets.py --only pdf # only direct PDF links
    python3 datasheets/fetch_datasheets.py --list     # print what would be fetched

Needs only the Python standard library. Files go to datasheets/<component_id>/.
Non-PDF links (product/documentation pages) are saved as .html for offline reference.
A report is written to datasheets/fetch_report.json.
"""
import argparse
import json
import pathlib
import re
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
LIB = HERE.parent / "components" / "components.json"
UA = "Mozilla/5.0 (robotics-reference-pack datasheet fetcher)"


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:60] or "file"


def fetch(url: str, dest_base: pathlib.Path) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except Exception as exc:  # noqa: BLE001 - report every failure, keep going
        return {"url": url, "ok": False, "error": str(exc)}
    is_pdf = data[:4] == b"%PDF" or "pdf" in ctype.lower()
    dest = dest_base.with_suffix(".pdf" if is_pdf else ".html")
    dest.write_bytes(data)
    return {"url": url, "ok": True, "file": str(dest.relative_to(HERE)), "bytes": len(data), "pdf": is_pdf}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["pdf"], help="only links that end in .pdf")
    ap.add_argument("--list", action="store_true", help="list links without downloading")
    args = ap.parse_args()

    lib = json.loads(LIB.read_text())
    jobs = []
    for comp in lib["components"]:
        for ds in comp.get("datasheets", []):
            url = ds["url"]
            if args.only == "pdf" and ".pdf" not in url.lower():
                continue
            jobs.append((comp["id"], ds["label"], url))

    if args.list:
        for cid, label, url in jobs:
            print(f"{cid:28s} {label[:40]:40s} {url}")
        return 0

    report = []
    for cid, label, url in jobs:
        folder = HERE / cid
        folder.mkdir(exist_ok=True)
        result = fetch(url, folder / slug(label))
        result.update({"component": cid, "label": label})
        report.append(result)
        status = "ok " if result["ok"] else "ERR"
        print(f"[{status}] {cid}: {label} -> {result.get('file', result.get('error'))}")
        time.sleep(0.5)

    (HERE / "fetch_report.json").write_text(json.dumps(report, indent=2))
    failed = [r for r in report if not r["ok"]]
    print(f"\n{len(report) - len(failed)}/{len(report)} downloaded. Failures listed in fetch_report.json.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
