#!/usr/bin/env python3
"""Cluster-resampling uncertainty for the quoted held-out rho* endpoints.

The paper quotes rho* over the valid held-out cells as a range, 0.2 to 0.75, and each
endpoint is a bare grid value from one pass of e4_power_heldout at n_splice=300. Review
objected that the project's central normative claim is that a bound should accompany
every null, while its own quoted rho* values carry no uncertainty at all. This script
attaches it for the quoted cells: the two 0.2-endpoint cells and the 0.75 cell.

Method. The committed e4 splice loop is reproduced VERBATIM first -- including its
`donor_by_key.get(r.key, r)` behaviour, which silently keeps a base row when the donor
archive lacks the item (the shipped power.py refuses that case, PMK-POW-001; the
discrepancy is counted and declared here rather than repaired, because repairing it
would move a committed artifact). The script refuses to continue unless every
power_by_rho value matches power_heldout.json. Then the declared archive's 74 clusters
are resampled with replacement (B=1000, relabelled `name#j`, rows relabelled so
duplicate clusters swap independently; the donor stays whole and follows through
item-key pairing, since resampling it independently would break the pairing the splice
requires). Per resample the whole rho* procedure is re-run at the SHIPPED threshold:
the estimand is the shipped instrument's rho* over the cluster population, and the
rho=0 self-check is re-evaluated at the committed tolerance so a resample can also come
out invalid.

rho* lives on the grid, so the answer is a grid-value frequency table and a percentile
interval in grid space, with `None` (never reaches power 0.8) ordered above 1.0 and
self-check failures excluded from the interval but declared; a failure share above 10%
refuses the interval outright. A duplicate-free 51-of-74 subsample arm (the
kt2_bootstrap precedent) is reported beside it.

Everything is exact cluster-sum arithmetic: T is a difference of per-row means, so a
draw's statistic is computable from per-cluster score sums, and the RNG consumption of
cluster_subset and the swap shuffle is replicated name-for-name (asserted against the
row-level loop during reconciliation).

Zero API calls: reads the sibling checkout's archives and the shipped model only.

Usage:  .venv/bin/python validation/angle_a/rho_star_ci.py [--source PATH] [--write]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.archive import read_archive  # noqa: E402
from punchmark.calibrate import (  # noqa: E402
    ScoredRow,
    ScoredSet,
    cluster_subset,
    lookup_threshold,
    t_statistic,
)
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import fitted_from_params  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.modelfile import read_model  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402

CAL_DIR = ROOT / "calibration" / "spaghetti"
OUT = HERE / "derived" / "rho_star_uncertainty.json"
SEED = 20260803
FAR = 0.01
RHO_GRID = (0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)   # e4's grid, run.py:492
N_SPLICE = 300                                            # run.py:493
B = 1000
SUBSAMPLE_K = 51                                          # kt2_bootstrap precedent
POWER_TARGET = 0.8
SELFCHECK_TOL = FAR + 0.02                                # run.py:544

ROUTES = (
    "deepseek-ai/DeepSeek-V4-Flash",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
)
CANDIDATES = CandidateSet(routes=tuple(sorted(ROUTES)))
TASK_ALIAS = {"comprehend_test": "comprehend", "refactor_test": "refactor_dev"}

# The quoted cells: both 0.2 endpoints and the 0.75 endpoint of the valid range.
CELLS = [
    ("comprehend_test", "meta-llama/Llama-3.3-70B-Instruct-Turbo",
     "meta-llama/Meta-Llama-3.1-8B-Instruct", 0.2),
    ("comprehend_test", "meta-llama/Llama-3.3-70B-Instruct-Turbo",
     "mistralai/Mistral-Small-3.2-24B-Instruct-2506", 0.2),
    ("comprehend_test", "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
     "meta-llama/Meta-Llama-3.1-8B-Instruct", 0.75),
]

# Ordering of outcomes for the grid-space percentile interval. None means "no grid
# value reaches the power target", which is strictly worse than a full swap.
ORDER = {str(r): i for i, r in enumerate(RHO_GRID)}
ORDER["None"] = len(RHO_GRID)


def load_scored(source: Path, task: str, route: str, fitted) -> ScoredSet:
    path = source / "bench" / "out" / "g3" / f"{task}__{route.replace('/', '-')}.jsonl.gz"
    rs = read_archive(path, CANDIDATES)
    rs = load_and_attach(rs, path, CAL_DIR / "sidecars")
    rows = rs.valid_rows
    scored = fitted.score_rows(rows, TASK_ALIAS[task])
    return ScoredSet(
        route=rs.route, task=TASK_ALIAS[task], source_name=rs.source_name,
        rows=tuple(ScoredRow(key=r.item_key, cluster=r.cluster, scores=s)
                   for r, s in zip(rows, scored, strict=True)),
    )


class CellArithmetic:
    """Per-cluster sums for base and donor-aligned rows, making every splice draw a
    names-only computation whose RNG consumption matches the row-level loop."""

    def __init__(self, base: ScoredSet, donor: ScoredSet):
        self.declared = base.route
        self.task = base.task
        donor_by_key = {r.key: r for r in donor.rows}
        self.base_sums: dict[str, dict[str, float]] = {}
        self.swap_sums: dict[str, dict[str, float]] = {}
        self.counts: dict[str, int] = {}
        self.kept_rows_missing_donor = 0
        for name, rows in base.clusters.items():
            b_acc = dict.fromkeys(CANDIDATES.routes, 0.0)
            s_acc = dict.fromkeys(CANDIDATES.routes, 0.0)
            for r in rows:
                d = donor_by_key.get(r.key)
                if d is None:
                    self.kept_rows_missing_donor += 1
                    d = r  # the committed loop's silent keep, reproduced knowingly
                for c in CANDIDATES.routes:
                    b_acc[c] += r.scores[c]
                    s_acc[c] += d.scores[c]
            self.base_sums[name] = b_acc
            self.swap_sums[name] = s_acc
            self.counts[name] = len(rows)

    def draw_t(self, cluster_map: dict[str, str], m: int, rng: random.Random,
               rho: float) -> float:
        """One splice draw over a (possibly resampled) cluster map {label: source
        cluster}. Replicates cluster_subset + the e4 swap in names, consuming the RNG
        identically: sorted labels, shuffle, accumulate to >= m; then sorted subset
        labels, shuffle, accumulate whole clusters to >= rho * n."""
        labels = sorted(cluster_map)
        rng.shuffle(labels)
        chosen: list[str] = []
        n = 0
        for lb in labels:
            if n >= m:
                break
            chosen.append(lb)
            n += self.counts[cluster_map[lb]]
        swapped: set[str] = set()
        if rho > 0:
            names = sorted(chosen)
            rng.shuffle(names)
            target = rho * n
            n_sw = 0
            for nm in names:
                if n_sw >= target:
                    break
                swapped.add(nm)
                n_sw += self.counts[cluster_map[nm]]
        means = {}
        for c in CANDIDATES.routes:
            tot = 0.0
            for lb in chosen:
                src = cluster_map[lb]
                tot += (self.swap_sums if lb in swapped else self.base_sums)[src][c]
            means[c] = tot / n
        declared = means[self.declared]
        best_alt = max(v for c, v in means.items() if c != self.declared)
        return declared - best_alt

    def rho_star(self, cluster_map: dict[str, str], m: int, threshold: float,
                 seed_parts: tuple) -> tuple[float | None, bool, dict[str, float]]:
        """The full e4 procedure on one cluster map: powers per rho ascending with
        early stop after the first crossing; returns (rho*, selfcheck_ok, powers)."""
        powers: dict[str, float] = {}
        rho_min = None
        for rho in RHO_GRID:
            if rho_min is not None and rho > 0:
                break
            flags = 0
            for i in range(N_SPLICE):
                rng = random.Random(derive_seed(*seed_parts, f"rho={rho}", i, SEED))
                t = self.draw_t(cluster_map, m, rng, rho)
                flags += int(t < threshold)
            power = flags / N_SPLICE
            powers[str(rho)] = round(power, 4)
            if rho > 0 and rho_min is None and power >= POWER_TARGET:
                rho_min = rho
        return rho_min, powers["0.0"] <= SELFCHECK_TOL, powers


def grid_interval(outcomes: list[str]) -> list[str]:
    ordered = sorted(outcomes, key=lambda o: ORDER[o])
    lo = ordered[max(0, int(0.025 * len(ordered)))]
    hi = ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))]
    return [lo, hi]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(ROOT.parent / "Spaghetti-Architect"))
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    source = Path(args.source)

    doc = read_model(CAL_DIR / "goldens" / "default.pmk-model.json")
    fitted = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)
    committed = {
        (r["task"], r["declared"], r["substitute"]): r
        for r in json.loads(
            (HERE / "derived" / "power_heldout.json").read_text(encoding="utf-8")
        )["results"]
    }

    cells_out = []
    for task, declared, substitute, quoted in CELLS:
        base = load_scored(source, task, declared, fitted)
        donor = load_scored(source, task, substitute, fitted)
        cell = CellArithmetic(base, donor)
        op = lookup_threshold(doc.operating_points, cell.task, declared, FAR,
                              len(base.rows))
        assert op is not None
        com = committed[(cell.task, declared, substitute)]
        print(f"\n{cell.task}  {declared}  <-  {substitute}   (m={op.m}, "
              f"quoted rho*={quoted}, donor-missing rows kept: "
              f"{cell.kept_rows_missing_donor})")

        # RECONCILIATION: names-level arithmetic must reproduce the committed run,
        # and the row-level loop must agree with the names-level one.
        identity = {name: name for name in cell.counts}
        seed_parts = ("heldout-splice", cell.task, declared, substitute)
        rho_check = 0.2
        rng = random.Random(derive_seed(*seed_parts, f"rho={rho_check}", 0, SEED))
        t_names = cell.draw_t(identity, op.m, rng, rho_check)
        rng = random.Random(derive_seed(*seed_parts, f"rho={rho_check}", 0, SEED))
        subset = cluster_subset(base.clusters, op.m, rng)
        donor_by_key = {r.key: r for r in donor.rows}
        names = sorted({r.cluster for r in subset})
        rng.shuffle(names)
        target = rho_check * len(subset)
        swapped: set[str] = set()
        n_sw = 0
        for nm in names:
            if n_sw >= target:
                break
            swapped.add(nm)
            n_sw += sum(1 for r in subset if r.cluster == nm)
        subset = tuple(donor_by_key.get(r.key, r) if r.cluster in swapped else r
                       for r in subset)
        t_rows = t_statistic(subset, declared, CANDIDATES.routes)
        if abs(t_names - t_rows) > 1e-12:
            raise SystemExit(f"names-level vs row-level mismatch: {t_names} {t_rows}")

        powers_full: dict[str, float] = {}
        for rho in RHO_GRID:
            flags = 0
            for i in range(N_SPLICE):
                rng = random.Random(derive_seed(*seed_parts, f"rho={rho}", i, SEED))
                flags += int(cell.draw_t(identity, op.m, rng, rho) < op.threshold)
            powers_full[str(rho)] = round(flags / N_SPLICE, 4)
        if powers_full != com["power_by_rho"]:
            raise SystemExit(
                f"reconciliation failed: {powers_full} vs {com['power_by_rho']}"
            )
        print("  reconciled: all 8 power_by_rho values match power_heldout.json")

        # BOOTSTRAP, with replacement.
        names_sorted = sorted(cell.counts)
        outcomes: list[str] = []
        n_selfcheck_fail = 0
        freq: dict[str, int] = {}
        for b in range(B):
            rng = random.Random(derive_seed("a5-boot-resample", cell.task, declared,
                                            substitute, b, SEED))
            picks = [rng.choice(names_sorted) for _ in range(len(names_sorted))]
            cmap = {f"{nm}#{j}": nm for j, nm in enumerate(picks)}
            rho_b, ok, _ = cell.rho_star(
                cmap, op.m, op.threshold,
                ("a5-boot", cell.task, declared, substitute, b),
            )
            if not ok:
                n_selfcheck_fail += 1
                continue
            key = "None" if rho_b is None else str(rho_b)
            outcomes.append(key)
            freq[key] = freq.get(key, 0) + 1

        # SENSITIVITY: duplicate-free 51-of-74 subsample.
        outcomes_wor: list[str] = []
        n_fail_wor = 0
        freq_wor: dict[str, int] = {}
        for b in range(B):
            rng = random.Random(derive_seed("a5-wor-resample", cell.task, declared,
                                            substitute, b, SEED))
            picks = rng.sample(names_sorted, SUBSAMPLE_K)
            cmap = {nm: nm for nm in picks}
            rho_b, ok, _ = cell.rho_star(
                cmap, op.m, op.threshold,
                ("a5-wor", cell.task, declared, substitute, b),
            )
            if not ok:
                n_fail_wor += 1
                continue
            key = "None" if rho_b is None else str(rho_b)
            outcomes_wor.append(key)
            freq_wor[key] = freq_wor.get(key, 0) + 1

        fail_share = n_selfcheck_fail / B
        interval = None if fail_share > 0.10 else grid_interval(outcomes)
        verdict = (
            "UNDETERMINED" if interval is None else
            "STABLE" if interval[0] == interval[1] == str(quoted) else
            "SPANS_GRID"
        )
        print(f"  bootstrap: {dict(sorted(freq.items(), key=lambda x: ORDER[x[0]]))}"
              f"  selfcheck-fail {fail_share:.1%}  interval {interval}  -> {verdict}")

        cells_out.append({
            "task": cell.task,
            "declared": declared,
            "substitute": substitute,
            "m": op.m,
            "far": FAR,
            "committed_rho_star": quoted,
            "reconciliation_power_by_rho_matches": True,
            "donor_missing_key_rows_kept_silently": cell.kept_rows_missing_donor,
            "n_clusters": len(cell.counts),
            "B": B,
            "rho_star_frequencies": {
                k: round(v / max(1, len(outcomes)), 4)
                for k, v in sorted(freq.items(), key=lambda x: ORDER[x[0]])
            },
            "selfcheck_fail_share": round(fail_share, 4),
            "grid_interval_95": interval,
            "subsample_wor": {
                "k_of_n": [SUBSAMPLE_K, len(cell.counts)],
                "rho_star_frequencies": {
                    k: round(v / max(1, len(outcomes_wor)), 4)
                    for k, v in sorted(freq_wor.items(), key=lambda x: ORDER[x[0]])
                },
                "selfcheck_fail_share": round(n_fail_wor / B, 4),
                "grid_interval_95":
                    None if n_fail_wor / B > 0.10 else grid_interval(outcomes_wor),
            },
            "verdict": verdict,
        })

    body = {
        "punchmark_schema": "angle_a_rho_star_uncertainty/v1",
        "seed": SEED,
        "n_splice": N_SPLICE,
        "rho_grid": list(RHO_GRID),
        "power_target": POWER_TARGET,
        "resampling_unit": (
            "declared archive's clusters (base samples) with replacement, rows "
            "relabelled per copy; donor whole, paired by item key; shipped "
            "threshold fixed"
        ),
        "committed_loop_discrepancy": (
            "the committed e4 loop keeps a base row silently when the donor lacks "
            "its item key (run.py, donor_by_key.get(r.key, r)); the shipped "
            "power.py refuses that case (PMK-POW-001). Reproduced knowingly for "
            "reconciliation; per-cell counts recorded as "
            "donor_missing_key_rows_kept_silently"
        ),
        "cells": cells_out,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(body))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/rho_star_uncertainty.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
