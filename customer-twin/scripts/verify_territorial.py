"""Standalone verification of the territorial normalization pipeline.

Run from the project root::

    python scripts/verify_territorial.py

The script loads the processed parquet, runs detection, normalizes the
territorial fields and prints coverage stats. Useful as a smoke test before
demos: if anything regresses (e.g. a new dataset breaks the alias table) the
output makes it obvious.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# Allow running as `python scripts/verify_territorial.py` from the project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from etl.pipeline import load_precio_medio, load_sow, load_weekly  # noqa: E402
from etl.territorial import (  # noqa: E402
    CCAA_OFICIALES,
    PROVINCIAS,
    normalize_provincia,
)
from models.signal_detector import run_detection  # noqa: E402


def _bar(n: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return ""
    filled = int(round((n / total) * width))
    return "█" * filled + "·" * (width - filled)


def main() -> int:
    print("=== Territorial verification ===")
    print(f"Project root: {ROOT}")

    weekly = load_weekly()
    sow = load_sow()
    precio = load_precio_medio()

    raw_provincias = weekly["provincia"].dropna().unique().tolist()
    print(f"\nRaw provincias in dataset: {len(raw_provincias)}")
    unmapped_raw = [p for p in raw_provincias if normalize_provincia(p).provincia is None]
    print(f"Raw provincias that fail to normalize: {len(unmapped_raw)}")
    if unmapped_raw:
        for p in unmapped_raw:
            print(f"  - {p!r}")

    print("\nRunning detection (cap=1500 clients)…")
    sigs = run_detection(weekly, sow, precio, max_clients=1500)
    total = len(sigs)
    print(f"Total signals: {total}")

    mapped = [s for s in sigs if s.provincia and s.provincia in PROVINCIAS]
    unmapped = [s for s in sigs if not (s.provincia and s.provincia in PROVINCIAS)]
    coverage = len(mapped) / total if total else 1.0

    print(f"  with canonical provincia : {len(mapped):>5}  ({coverage:.1%})")
    print(f"  with comunidad autónoma  : {sum(1 for s in mapped if s.comunidad_autonoma):>5}")
    print(f"  sin ubicación            : {len(unmapped):>5}")

    by_source: Counter = Counter(s.territorial_source or "unknown" for s in sigs)
    print("\nBy territorial source:")
    for src, n in by_source.most_common():
        print(f"  {src:<10} {n:>5}  {_bar(n, total)}")

    by_ccaa = Counter(s.comunidad_autonoma for s in mapped)
    print(f"\nTop 10 comunidades autónomas (of {len(by_ccaa)} present):")
    for ccaa, n in by_ccaa.most_common(10):
        print(f"  {ccaa:<28} {n:>5}  {_bar(n, by_ccaa.most_common(1)[0][1])}")

    by_provincia = Counter(s.provincia for s in mapped)
    print(f"\nTop 15 provincias (of {len(by_provincia)} present):")
    for prov, n in by_provincia.most_common(15):
        print(f"  {prov:<28} {n:>5}  {_bar(n, by_provincia.most_common(1)[0][1])}")

    # Sanity: no canonical CCAA should be missing if we have wide coverage.
    missing_ccaa = set(CCAA_OFICIALES) - set(by_ccaa.keys())
    if missing_ccaa:
        print(f"\nCCAA without alerts: {sorted(missing_ccaa)}")

    print("\nAlertas no ubicadas — primeros 10 raw values:")
    raw_unmapped = Counter(s.provincia_raw or "<vacío>" for s in unmapped)
    for raw, n in raw_unmapped.most_common(10):
        print(f"  {raw!r:<24} {n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
