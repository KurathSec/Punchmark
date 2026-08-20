#!/usr/bin/env python3
"""Cluster-resampling uncertainty for the corrected load-bearing rho* of 0.5.

The paper's section on the spurious rho*=0.05 ends with the corrected value: at m=50,
FAR 0.01, the load-bearing pair on the long task resolves at rho* = 0.5, the pair-worst
of its two directions (0.3 for deepinfra as declared, 0.5 for together). That value is
one grid point from one pass, and review asked what uncertainty it carries.

This bootstrap is SCORE-CONDITIONAL by necessity, not convenience. Refitting the
detector per resample would put a duplicated cluster's content into both cross-fitting
folds, which is exactly the leakage crossfit_scored exists to prevent (the fold map is
keyed on cluster names precisely so shared item content cannot straddle folds), so a
full-pipeline bootstrap is statistically wrong here rather than merely expensive. The
resamples therefore condition on the committed out-of-fold scores; the uncaptured
detector-refit variance is declared, not hidden.

Per resample: the pair's 40 shared refactor_dev clusters are drawn jointly with
replacement (the archives answer the same 75 items, so clusters pair by name and the
splice's item-key pairing survives resampling); the m=50 null is rebuilt from the
resampled declared archive (5,000 draws, conservative 1% quantile, exactly the shipped
null construction); the rho=0 self-check is re-run at the shipped tolerance; and the
refusing power.py splice is re-run over the shipped rho grid in both directions,
pair-worst rho* per resample.

Reconciliation before any new number, in two stages: (1) power_analysis on the
recomputed calibration must reproduce every committed m=50 rho* in
angle_c_evaluation.json's c3_power; (2) this script's names-level arithmetic, run with
power.py's exact seed labels on the identity resample, must reproduce the pair's two
directions (0.3 and 0.5) again. Only then do the fresh-labelled resamples run.

Reads the purchased archives only; issues no requests.

Usage:  .venv/bin/python validation/angle_c/rho_star_ci.py [--write]
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
sys.path.insert(0, str(HERE))

from evaluate import (  # noqa: E402  (angle_c's own module, not foreign code)
    LOAD_BEARING,
    SIDE_CANDIDATES,
    load_purchased,
)

from punchmark.calibrate import (  # noqa: E402
    CalibrationConfig,
    calibrate,
    conservative_quantile,
)
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import build_detector  # noqa: E402
from punchmark.power import (  # noqa: E402
    PowerConfig,
    _selfcheck_tolerance,
    power_analysis,
)

OUT = HERE / "derived" / "rho_star_uncertainty.json"
SEED = 20260806
FAR = 0.01
TASK = "refactor_dev"
M = 50
N_NULL = 5000
N_SPLICE = 400
RHO_GRID = (0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)   # PowerConfig default
POWER_TARGET = 0.8
B = 500

ORDER = {str(r): i for i, r in enumerate(RHO_GRID)}
ORDER["None"] = len(RHO_GRID)


class PairArithmetic:
    """Per-cluster score sums for both pair archives, aligned by cluster name."""

    def __init__(self, oof_by_route: dict):
        self.routes = tuple(SIDE_CANDIDATES.routes)
        self.sums: dict[str, dict[str, dict[str, float]]] = {}
        self.counts: dict[str, int] = {}
        keysets: dict[str, dict[str, frozenset]] = {}
        for label in LOAD_BEARING:
            ss = oof_by_route[label]
            self.sums[label] = {}
            keysets[label] = {}
            for name, rows in ss.clusters.items():
                acc = dict.fromkeys(self.routes, 0.0)
                for r in rows:
                    for c in self.routes:
                        acc[c] += r.scores[c]
                self.sums[label][name] = acc
                keysets[label][name] = frozenset(r.key for r in rows)
                self.counts[name] = len(rows)
        a, b = LOAD_BEARING
        if sorted(keysets[a]) != sorted(keysets[b]):
            raise SystemExit("pair archives do not share cluster names")
        for name in keysets[a]:
            if keysets[a][name] != keysets[b][name]:
                raise SystemExit(f"cluster {name}: item keys differ across the pair")

    def draw_t(self, declared: str, donor: str, cluster_map: dict[str, str],
               rng: random.Random, rho: float) -> float:
        """cluster_subset + power.py's _swap, replicated in names with identical RNG
        consumption: sorted labels, shuffle, accumulate to >= M rows; then sorted
        subset labels, shuffle, accumulate whole clusters to >= rho * n rows."""
        labels = sorted(cluster_map)
        rng.shuffle(labels)
        chosen: list[str] = []
        n = 0
        for lb in labels:
            chosen.append(lb)
            n += self.counts[cluster_map[lb]]
            if n >= M:
                break
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
        for c in self.routes:
            tot = 0.0
            for lb in chosen:
                src = cluster_map[lb]
                tot += self.sums[donor if lb in swapped else declared][src][c]
            means[c] = tot / n
        d = means[declared]
        best_alt = max(v for c, v in means.items() if c != declared)
        return d - best_alt

    def procedure(self, cluster_map: dict[str, str], labels: dict) -> tuple:
        """Null -> self-check -> splice grid, pair-worst rho*. `labels` maps each
        stage to its seed-part tuple prefix (i is appended)."""
        directions = {}
        for declared, donor in (LOAD_BEARING, tuple(reversed(LOAD_BEARING))):
            null = []
            for i in range(N_NULL):
                rng = random.Random(derive_seed(*labels["null"](declared), i, SEED))
                null.append(self.draw_t(declared, donor, cluster_map, rng, 0.0))
            thr = conservative_quantile(null, FAR)
            zero = []
            for i in range(N_SPLICE):
                rng = random.Random(derive_seed(*labels["rho0"](declared), i, SEED))
                zero.append(self.draw_t(declared, donor, cluster_map, rng, 0.0))
            rate = sum(1 for t in zero if t < thr) / len(zero)
            selfcheck_ok = rate <= _selfcheck_tolerance(FAR, len(zero))
            rho_min = None
            for rho in RHO_GRID:
                flags = 0
                for i in range(N_SPLICE):
                    rng = random.Random(
                        derive_seed(*labels["splice"](declared, donor, rho), i, SEED)
                    )
                    flags += int(self.draw_t(declared, donor, cluster_map, rng, rho)
                                 < thr)
                if flags / N_SPLICE >= POWER_TARGET:
                    rho_min = rho
                    break
            directions[declared] = {
                "rho_star": rho_min, "selfcheck_ok": selfcheck_ok,
                "threshold": round(thr, 6),
            }
        vals = [d["rho_star"] for d in directions.values()]
        worst = None if any(v is None for v in vals) else max(vals)
        ok = all(d["selfcheck_ok"] for d in directions.values())
        return worst, ok, directions


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    committed = json.loads(
        (HERE / "derived" / "angle_c_evaluation.json").read_text(encoding="utf-8")
    )["c3_power"]

    detector = build_detector("chargram", view="CANON@1")
    cal_cfg = CalibrationConfig(far_grid=(0.001, 0.005, 0.01, 0.05, 0.1),
                                m_grid=(25, M), n_null=N_NULL, seed=SEED,
                                min_clusters=8)
    purchased = load_purchased()
    cal = calibrate(detector, purchased, SIDE_CANDIDATES, cal_cfg)

    # STAGE 1: the row-level pipeline reproduces every committed m=50 rho*.
    pow_cfg = PowerConfig(n_splice=N_SPLICE, power_target=POWER_TARGET, seed=SEED)
    res = power_analysis(cal.oof_scored, SIDE_CANDIDATES, cal.operating_points,
                         cal_cfg, pow_cfg)
    for p in res.power_points:
        if p.far != FAR or p.m != M:
            continue
        key = f"{p.task}|{p.declared} substituted_by {p.substitute}|m={p.m}"
        if committed["rho_min_by_pair"][key] != p.rho_min:
            raise SystemExit(f"stage-1 reconciliation failed at {key}: "
                             f"{p.rho_min} vs {committed['rho_min_by_pair'][key]}")
    print("stage 1: power_analysis reproduces all committed m=50 rho* values")

    oof_by_route = {ss.route: ss for ss in cal.oof_scored if ss.task == TASK}
    pair = PairArithmetic(oof_by_route)
    src_name = {label: oof_by_route[label].source_name for label in LOAD_BEARING}

    # STAGE 2: names-level identity run with power.py's EXACT seed labels.
    identity = {name: name for name in pair.counts}
    exact_labels = {
        "null": lambda d: ("null", TASK, src_name[d], M),
        "rho0": lambda d: ("power-rho0", TASK, d, src_name[d], M),
        "splice": lambda d, s, rho: ("power", TASK, d, s, src_name[d], M,
                                     f"rho={rho}"),
    }
    worst0, ok0, dirs0 = pair.procedure(identity, exact_labels)
    want = committed["load_bearing_pair_rho_at_m"][TASK]
    a, b = LOAD_BEARING
    want_dirs = {
        a: committed["rho_min_by_pair"][f"{TASK}|{a} substituted_by {b}|m={M}"],
        b: committed["rho_min_by_pair"][f"{TASK}|{b} substituted_by {a}|m={M}"],
    }
    for d, w in want_dirs.items():
        if dirs0[d]["rho_star"] != w:
            raise SystemExit(f"stage-2 reconciliation failed: {d} gives "
                             f"{dirs0[d]['rho_star']}, committed {w}")
    if worst0 != want or not ok0:
        raise SystemExit(f"stage-2 pair-worst {worst0} != committed {want}")
    print(f"stage 2: names-level identity run reproduces the pair "
          f"({want_dirs[a]}, {want_dirs[b]}) -> pair-worst {worst0}")

    # BOOTSTRAP, fresh labels, joint pair resample.
    names_sorted = sorted(pair.counts)
    outcomes: list[str] = []
    freq: dict[str, int] = {}
    n_selfcheck_fail = 0
    for bb in range(B):
        rng = random.Random(derive_seed("a5c-resample", TASK, bb, SEED))
        picks = [rng.choice(names_sorted) for _ in range(len(names_sorted))]
        cmap = {f"{nm}#{j}": nm for j, nm in enumerate(picks)}
        boot_labels = {
            "null": lambda d, _b=bb: ("a5c-null", TASK, d, _b),
            "rho0": lambda d, _b=bb: ("a5c-rho0", TASK, d, _b),
            "splice": lambda d, s, rho, _b=bb: ("a5c-splice", TASK, d, s, _b,
                                                f"rho={rho}"),
        }
        worst, ok, _ = pair.procedure(cmap, boot_labels)
        if not ok:
            n_selfcheck_fail += 1
            continue
        key = "None" if worst is None else str(worst)
        outcomes.append(key)
        freq[key] = freq.get(key, 0) + 1

    fail_share = n_selfcheck_fail / B
    if fail_share > 0.10:
        interval = None
        verdict = "UNDETERMINED"
    else:
        ordered = sorted(outcomes, key=lambda o: ORDER[o])
        interval = [ordered[max(0, int(0.025 * len(ordered)))],
                    ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))]]
        verdict = ("STABLE" if interval[0] == interval[1] == str(want)
                   else "SPANS_GRID")
    freq_sorted = {k: round(v / max(1, len(outcomes)), 4)
                   for k, v in sorted(freq.items(), key=lambda x: ORDER[x[0]])}
    print(f"bootstrap: {freq_sorted}  selfcheck-fail {fail_share:.1%}  "
          f"interval {interval}  -> {verdict}")

    body = {
        "punchmark_schema": "angle_c_rho_star_uncertainty/v1",
        "seed": SEED,
        "task": TASK,
        "pair": list(LOAD_BEARING),
        "m": M,
        "far": FAR,
        "n_null": N_NULL,
        "n_splice": N_SPLICE,
        "rho_grid": list(RHO_GRID),
        "B": B,
        "committed_pair_worst_rho_star": want,
        "committed_directions": want_dirs,
        "reconciliation": {
            "power_analysis_matches_all_committed_m50_cells": True,
            "names_level_identity_matches_pair": True,
        },
        "method": (
            "score-conditional cluster bootstrap: the pair's 40 shared clusters "
            "resampled jointly with replacement; per resample the m=50 null is "
            "rebuilt (5000 draws, conservative quantile), the rho=0 self-check "
            "re-run at the shipped tolerance, and the refusing splice re-run in "
            "both directions; pair-worst rho* per resample. Conditioning on the "
            "committed out-of-fold scores is forced, not chosen: a per-resample "
            "refit would place duplicated cluster content in both cross-fitting "
            "folds, the leakage crossfit_scored exists to prevent, so the "
            "detector-refit variance is declared uncaptured rather than smuggled "
            "in through a broken resampling scheme"
        ),
        "rho_star_frequencies": freq_sorted,
        "selfcheck_fail_share": round(fail_share, 4),
        "grid_interval_95": interval,
        "verdict": verdict,
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
