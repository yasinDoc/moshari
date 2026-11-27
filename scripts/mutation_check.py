"""Mutation check for S2: plant known bugs and confirm the tests catch every one.

Each mutant is one small, realistic mistake in the routing engine, the allocation engine or
the Hospital beds page. For each, the project is copied to a temporary folder, the mistake
is written into the copy, and the related test files are run there. The tests must FAIL
(pytest exit 1): that means the bug was caught ("killed"). If they still pass, the bug
"survived", and a guarantee is not really tested.

    python scripts/mutation_check.py            # all mutants
    python scripts/mutation_check.py R1 A2      # just these
    python scripts/mutation_check.py --list     # show the mutants

Prints one line per mutant and "MUTATION CHECK: <killed>/<total> killed". Exits 0 only when
every mutant is killed. Your working copy is never changed. Takes a few minutes.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".claude", "node_modules", ".mypy_cache",
        ".coverage", "htmlcov"}

ROUTING = "src/moshari/routing.py"
ALLOCATION = "src/moshari/allocation.py"
PAGE = "ui/views/hospital.py"
ROUTING_TESTS = ["tests/test_routing.py"]
ALLOCATION_TESTS = ["tests/test_allocation.py", "tests/test_allocation_engine.py"]
PAGE_TESTS = ["tests/test_hospital_page.py"]


@dataclass(frozen=True)
class Mutant:
    id: str
    what: str
    file: str
    old: str
    new: str
    tests: tuple[str, ...]


MUTANTS = [
    # --- routing: the TASKS.md rules
    Mutant("R1", "transfers cross city boundaries", ROUTING,
           "for city, grp in wards.groupby(C.CITY_COL, sort=True):",
           'for city, grp in [("All", wards)]:', tuple(ROUTING_TESTS)),
    Mutant("R2", "receiver can be filled past its capacity", ROUTING,
           "moved = min(need, capacity[target] - load[target])", "moved = need", tuple(ROUTING_TESTS)),
    Mutant("R3", "nearest ward first instead of least loaded", ROUTING,
           "key=lambda w: (load[w] / capacity[w], _distance(sender, w), w))",
           "key=lambda w: (_distance(sender, w), w))", tuple(ROUTING_TESTS)),
    Mutant("R4", "smallest overflow handled first", ROUTING,
           "key=lambda w: (-overflow[w], w)", "key=lambda w: (overflow[w], w)", tuple(ROUTING_TESTS)),
    Mutant("R5", "capacity history not cut off at 2023", ROUTING,
           "hist = df[pd.to_datetime(df[C.DATE_COL]) <= pd.Timestamp(end)]", "hist = df", tuple(ROUTING_TESTS)),
    Mutant("R6", "negative deficits reported", ROUTING,
           'wards["net_deficit"] = (wards["beds_in_use"] - wards["bed_capacity"]).clip(lower=0).astype(int)',
           'wards["net_deficit"] = (wards["beds_in_use"] - wards["bed_capacity"]).astype(int)', tuple(ROUTING_TESTS)),
    Mutant("R7", "surge beds rounded up (counts beds that are not there)", ROUTING,
           "np.floor(cap * (1 + surge_pct / 100) + 1e-9)", "np.ceil(cap * (1 + surge_pct / 100) - 1e-9)",
           tuple(ROUTING_TESTS)),
    # --- allocation
    Mutant("A1", "ward id no longer breaks priority ties", ALLOCATION,
           "np.lexsort((df[C.WARD_COL].astype(str).to_numpy(), ", "np.lexsort((", tuple(ALLOCATION_TESTS)),
    Mutant("A2", "allocation can exceed stock", ALLOCATION,
           "give = min(int(need[i]), left)", "give = int(need[i])", tuple(ALLOCATION_TESTS)),
    Mutant("A3", "lowest priority served first", ALLOCATION,
           '-df["priority_score"].to_numpy()))', 'df["priority_score"].to_numpy()))', tuple(ALLOCATION_TESTS)),
    Mutant("A4", "first crew pass gives a ward all its crews", ALLOCATION,
           "            out[i] = 1\n", "            out[i] = crew_need[i]\n", tuple(ALLOCATION_TESTS)),
    Mutant("A5", "demand rounded down (understated)", ALLOCATION,
           'np.ceil(df["planned_cases"] * ratios.ratios[need_col] - 1e-9)',
           'np.floor(df["planned_cases"] * ratios.ratios[need_col] + 1e-9)', tuple(ALLOCATION_TESTS)),
    # --- the Hospital beds page
    Mutant("P1", "page uses the stand-in demand instead of allocate()", PAGE,
           "alloc = allocate(fc, state.service().wards) if allocate else beds_from_forecast(fc)",
           "alloc = beds_from_forecast(fc)", tuple(PAGE_TESTS)),
    Mutant("P2", "wrong patients-moved stat", PAGE,
           "f\"{int(transfers['patients'].sum()):,}\"", "f\"{len(transfers) + 1:,}\"", tuple(PAGE_TESTS)),
    Mutant("P3", "surge slider ignored", PAGE,
           "with_surge(bed_capacity(), surge_pct)", "with_surge(bed_capacity(), 0)", tuple(PAGE_TESTS)),
    Mutant("P4", "red list misses wards 1 bed short", PAGE,
           'short = show_w[show_w["net_deficit"] > 0]', 'short = show_w[show_w["net_deficit"] > 1]',
           tuple(PAGE_TESTS)),
]


def _copy_project() -> Path:
    dst = Path(tempfile.mkdtemp(prefix="moshari-mut-")) / "proj"
    shutil.copytree(ROOT, dst, ignore=lambda _d, names: [n for n in names if n in SKIP])
    return dst


def run_mutant(m: Mutant) -> tuple[str, str]:
    """Returns (verdict, detail). verdict is KILLED, SURVIVED or ERROR."""
    proj = _copy_project()
    try:
        f = proj / m.file
        text = f.read_text(encoding="utf-8")
        if text.count(m.old) != 1:
            return "ERROR", f"code to mutate found {text.count(m.old)} times in {m.file} (expected once)"
        f.write_text(text.replace(m.old, m.new), encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *m.tests],
                           cwd=proj, capture_output=True, text=True, timeout=900)
        if r.returncode == 1:
            failed = next((ln for ln in r.stdout.splitlines() if ln.startswith("FAILED")), "a test failed")
            return "KILLED", failed.removeprefix("FAILED ").split(" - ")[0]
        if r.returncode == 0:
            return "SURVIVED", "all selected tests still pass"
        return "ERROR", f"pytest exit {r.returncode}"
    except subprocess.TimeoutExpired:
        return "ERROR", "timed out"
    finally:
        shutil.rmtree(proj.parent, ignore_errors=True)


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for m in MUTANTS:
            print(f"{m.id:3} {m.file:28} {m.what}")
        return 0
    chosen = [m for m in MUTANTS if not argv or m.id in argv]
    unknown = set(argv) - {m.id for m in MUTANTS}
    if unknown or not chosen:
        print(f"Unknown mutant id(s): {', '.join(sorted(unknown)) or '(none chosen)'}. Use --list.")
        return 2
    start = time.time()
    workers = max(1, min(4, os.cpu_count() or 1))
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(run_mutant, chosen))
    for m, (verdict, detail) in zip(chosen, results):
        print(f"{verdict:8} {m.id:3} {m.what} ({m.file}) -> {detail}", flush=True)
    killed = sum(v == "KILLED" for v, _ in results)
    print(f"MUTATION CHECK: {killed}/{len(chosen)} killed in {time.time() - start:.0f}s")
    return 0 if killed == len(chosen) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
