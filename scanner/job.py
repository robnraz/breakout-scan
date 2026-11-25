#!/usr/bin/env python3
"""Daily scan used by GitHub Actions. Writes the static site beside the results."""

import shutil
import sys
from pathlib import Path

from server import CORE, EUROPE, FUTURES, US, US_ALL, run_scan

ROOT = Path(__file__).resolve().parent


def publish() -> None:
    site = ROOT / "site"
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(ROOT / "static", site)
    last = ROOT / "data" / "last.json"
    if last.exists():
        shutil.copy(last, site / "last.json")


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else "quick"
    if stage == "rest":
        stages = [("all", US_ALL)]
    else:
        stages = [
            ("core", list(dict.fromkeys([*CORE, *FUTURES]))),
            ("europe", EUROPE),
            ("us", US),
        ]
    for label, symbols in stages:
        try:
            print(f"stage {label} {len(symbols)}", flush=True)
            run_scan(symbols, label)
        except Exception as exc:
            print(f"stage {label} failed: {exc}", flush=True)
            break
    publish()


if __name__ == "__main__":
    main()
