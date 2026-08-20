#!/usr/bin/env python3
"""Power of the one-sample test against the provider swap, as a function of m.

one_sample.py records that a competitor-free fit statistic misses the cross-provider
swap at the purchased archive size on both tasks. Review asked the natural follow-up:
is that a property of the regime, or of m=75? If the test would flag the swap at larger
archives, "enumeration is required" weakens to "enumeration is required at these
archive sizes", which tells practitioners how large to make their archives.

Two curves, never merged, because they answer different questions:

1. MEASURED: power over cluster-respecting subsamples of the purchased archives at
   m in (20, 28, 38, 45, 53, 60, 68) rows. Honest label: this is power to flag
   subsamples of THIS swap archive against subsamples of THIS declared archive, and it
   mechanically inflates toward m=75 because drawing most of a 40-cluster archive
   shrinks both the null and the alternative onto their archive means (a
   finite-population effect, not fresh-archive power). The largest m points are
   retained deliberately to display that inflation.
2. MODEL-BASED: a fresh-archive extrapolation under Gaussian cluster means with the
   finite-population correction Var(m) = S^2 (1/c - 1/C), S fitted from the measured
   null sds with per-m residuals shown -- a bad fit voids the extrapolation and the
   artifact says so. The crossover m* solves sqrt(c) * delta = z_emp * S (power 0.5)
   and sqrt(c) * delta = z_emp * S + 0.8416 * S_swap (power 0.8), with z_emp the
   EMPIRICAL threshold-to-sd ratio of the committed null rather than the Gaussian
   2.326. The naive no-FPC figure is printed beside it, labelled, because it is what
   bare sqrt-m scaling gives and it understates m* by about half.

On the short task the question is a SIGN, not a crossover: the committed swap stat
sits above the null mean, so the one-sided test can never flag it at any m unless the
paired per-cluster shift's CI reaches below zero. That is measured, not assumed.

Reconciliation before any new number: the four full-archive stats must equal
derived/one_sample.json to all recorded digits.

Reads the purchased archives only; issues no requests.

Usage:  .venv/bin/python validation/angle_c/one_sample_power.py [--write]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.archive import read_archive  # noqa: E402
from punchmark.calibrate import crossfit_scored  # noqa: E402
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import build_detector  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402

ARCHIVES = HERE / "archives"
OUT = HERE / "derived" / "power_vs_m.json"
SEED = 20260806
TASKS = ("comprehend", "refactor_dev")
SLUG = "meta-llama-Llama-3.3-70B-Instruct-Turbo"
EIGHT = "meta-llama-Meta-Llama-3.1-8B-Instruct-Turbo"
FAR = 0.01
M_GRID = (20, 28, 38, 45, 53, 60, 68)
N_NULL_DRAWS = 10_000
N_ALT_DRAWS = 2_000
B_SHIFT = 2_000
Z_POWER_80 = 0.8416     # standard normal 80th percentile, for the power-0.8 crossover

A = "deepinfra/Llama-3.3-70B"
B_LBL = "together/Llama-3.3-70B"
C8 = "deepinfra/Llama-3.1-8B"
W2_LBL = "w2/Llama-3.3-70B"
ALT_LABELS = (B_LBL, C8, W2_LBL)


def load(provider: str, slug: str, task: str, label: str):
    path = ARCHIVES / provider / f"{task}__{slug}.jsonl.gz"
    if not path.exists():
        return None
    return dataclasses.replace(load_and_attach(read_archive(path), path), route=label)


class Sums:
    """Per-cluster sums of scores under the declared route A."""

    def __init__(self, ss):
        self.sums: dict[str, float] = {}
        self.counts: dict[str, int] = {}
        for name, rows in ss.clusters.items():
            self.sums[name] = sum(r.scores[A] for r in rows)
            self.counts[name] = len(rows)
        self.total_rows = sum(self.counts.values())
        self.n_clusters = len(self.counts)

    def stat_full(self) -> float:
        return sum(self.sums.values()) / self.total_rows

    def draw(self, m: int, rng: random.Random) -> tuple[float, int]:
        """cluster_subset's exact procedure in names: sorted keys, shuffle,
        accumulate whole clusters until >= m rows."""
        names = sorted(self.counts)
        rng.shuffle(names)
        tot = 0.0
        n = 0
        k = 0
        for nm in names:
            tot += self.sums[nm]
            n += self.counts[nm]
            k += 1
            if n >= m:
                break
        return tot / n, k


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    committed = json.loads(
        (HERE / "derived" / "one_sample.json").read_text(encoding="utf-8")
    )["results"]

    detector = build_detector("chargram", view="CANON@1")
    results: dict = {}

    for task in TASKS:
        sets = [load("deepinfra", SLUG, task, A), load("together", SLUG, task, B_LBL),
                load("deepinfra", EIGHT, task, C8), load("deepinfra-w2", SLUG, task, W2_LBL)]
        sets = [s for s in sets if s is not None]
        cands = CandidateSet(tuple(sorted(s.route for s in sets)))
        scored = {s.route: s for s in crossfit_scored(detector, sets, cands, SEED)}
        sums = {label: Sums(ss) for label, ss in scored.items()}

        # RECONCILIATION: full-archive stats equal the committed artifact.
        for label, sm in sums.items():
            want = committed[task]["archives"][label][
                "one_sample_stat_under_declared_route"]
            got = round(sm.stat_full(), 6)
            if got != want:
                raise SystemExit(f"reconciliation failed {task}/{label}: {got} != {want}")
        print(f"\n{task}: reconciled all 4 stats against one_sample.json "
              f"({sums[A].n_clusters} clusters, {sums[A].total_rows} rows)")

        # MEASURED curves.
        per_m = []
        for m in M_GRID:
            null_stats = []
            k_sum = 0
            for i in range(N_NULL_DRAWS):
                rng = random.Random(derive_seed("a1-null", task, m, i, SEED))
                s, k = sums[A].draw(m, rng)
                null_stats.append(s)
                k_sum += k
            null_stats.sort()
            thr = null_stats[max(0, int(FAR * len(null_stats)) - 1)]
            n_distinct = len(set(null_stats))
            realized_far = sum(1 for s in null_stats if s < thr) / len(null_stats)
            degenerate = n_distinct < 1000
            entry = {
                "m": m,
                "mean_clusters_per_draw": round(k_sum / N_NULL_DRAWS, 3),
                "n_null": N_NULL_DRAWS,
                "threshold": round(thr, 6),
                "null_mean": round(statistics.fmean(null_stats), 6),
                "null_sd": round(statistics.stdev(null_stats), 6),
                "null_n_distinct": n_distinct,
                "realized_far": round(realized_far, 4),
                "degenerate": degenerate,
                "undetermined": degenerate,
                "power": {},
                "alt_sd": {},
                "n_draws_alt": N_ALT_DRAWS,
            }
            for label in ALT_LABELS:
                if label not in sums:
                    continue
                flags = 0
                alt_stats = []
                for i in range(N_ALT_DRAWS):
                    rng = random.Random(derive_seed("a1-alt", task, label, m, i, SEED))
                    s, _ = sums[label].draw(m, rng)
                    alt_stats.append(s)
                    flags += int(s < thr)
                entry["power"][label] = round(flags / N_ALT_DRAWS, 4)
                entry["alt_sd"][label] = round(statistics.stdev(alt_stats), 6)
            per_m.append(entry)
            print(f"  m={m:3d}  thr {thr:+.4f}  sd {entry['null_sd']:.4f}  "
                  f"power {entry['power']}")

        # PAIRED PER-CLUSTER SHIFT delta = deepinfra minus together, row-weighted.
        shared = sorted(set(sums[A].counts) & set(sums[B_LBL].counts))
        d_num = {c: sums[A].sums[c] - sums[B_LBL].sums[c] for c in shared}
        d_cnt = {c: sums[A].counts[c] for c in shared}
        delta = sum(d_num.values()) / sum(d_cnt.values())
        boot = []
        for b in range(B_SHIFT):
            rng = random.Random(derive_seed("a1-shift-boot", task, b, SEED))
            picks = [rng.choice(shared) for _ in range(len(shared))]
            boot.append(sum(d_num[p] for p in picks) / sum(d_cnt[p] for p in picks))
        boot.sort()
        delta_ci = [round(boot[int(0.025 * B_SHIFT)], 6),
                    round(boot[int(0.975 * B_SHIFT) - 1], 6)]

        # MODEL-BASED extrapolation. S from the FPC fit Var(m) = S^2 (1/c - 1/C),
        # using non-degenerate m points only; per-m residuals recorded.
        C_total = sums[A].n_clusters
        s_hats = {}
        for e in per_m:
            if e["degenerate"]:
                continue
            c_m = e["mean_clusters_per_draw"]
            fpc = (1.0 / c_m) - (1.0 / C_total)
            if fpc <= 0:
                continue
            s_hats[e["m"]] = (e["null_sd"] ** 2 / fpc) ** 0.5
        s_hat = statistics.fmean(s_hats.values())
        s_resid = {str(m): round(v / s_hat - 1.0, 4) for m, v in s_hats.items()}
        fit_ok = all(abs(r) <= 0.15 for r in
                     (v / s_hat - 1.0 for v in s_hats.values()))

        s_swap_hats = []
        for e in per_m:
            if e["degenerate"] or B_LBL not in e["alt_sd"]:
                continue
            c_m = e["mean_clusters_per_draw"]
            fpc = (1.0 / c_m) - (1.0 / C_total)
            if fpc > 0:
                s_swap_hats.append((e["alt_sd"][B_LBL] ** 2 / fpc) ** 0.5)
        s_swap = statistics.fmean(s_swap_hats)

        # Empirical threshold-to-sd ratio of the COMMITTED split-half null.
        com = committed[task]
        z_emp = (com["null_mean"] - com["threshold_at_far"]) / com["null_sd"]

        rows_per_cluster = sums[A].total_rows / C_total

        def m_star(d: float, target80: bool, *, _z=z_emp, _s=s_hat, _sw=s_swap,
                   _rpc=rows_per_cluster) -> float | None:
            if d <= 0:
                return None
            need = _z * _s + (Z_POWER_80 * _sw if target80 else 0.0)
            c_star = (need / d) ** 2
            return round(c_star * _rpc, 1)

        extrapolation = {
            "model_based": True,
            "model": "gaussian-cluster-means-FPC",
            "S_hat": round(s_hat, 4),
            "S_hat_by_m": {str(m): round(v, 4) for m, v in s_hats.items()},
            "fit_residuals_by_m": s_resid,
            "fit_acceptable_within_15pct": fit_ok,
            "S_swap_hat": round(s_swap, 4),
            "z_empirical_committed_null": round(z_emp, 4),
            "z_gaussian_for_reference": 2.3263,
            "rows_per_cluster": round(rows_per_cluster, 4),
            "paired_shift_delta": round(delta, 6),
            "paired_shift_ci95": delta_ci,
            "n_shared_clusters": len(shared),
        }
        if not fit_ok:
            extrapolation["m_star"] = None
            extrapolation["verdict"] = (
                "UNDETERMINED: the sd(m) model does not fit the measured nulls "
                "within 15%; no crossover m is quotable beyond the measured range"
            )
        elif delta_ci[0] <= 0 <= delta_ci[1]:
            extrapolation["m_star"] = None
            extrapolation["verdict"] = (
                "UNDETERMINED: the paired shift's CI straddles zero, so whether any "
                "m could flag this swap is unresolved at this cluster count"
            )
        elif delta < 0:
            extrapolation["m_star"] = None
            extrapolation["verdict"] = (
                "NEVER: the swap fits the declared route no worse than the declared "
                "route's own material (paired shift below zero with CI excluding "
                "zero would be required to assert this; see ci)"
                if delta_ci[1] < 0 else "UNDETERMINED"
            )
        else:
            extrapolation["m_star"] = {
                "power_0.5_rows": {
                    "point": m_star(delta, False),
                    "ci95": [m_star(delta_ci[1], False), m_star(delta_ci[0], False)],
                },
                "power_0.8_rows": {
                    "point": m_star(delta, True),
                    "ci95": [m_star(delta_ci[1], True), m_star(delta_ci[0], True)],
                },
                "naive_no_fpc_power_0.5_rows": round(
                    ((z_emp * com["null_sd"] * ((C_total / 2.0) ** 0.5)) / delta) ** 2
                    * rows_per_cluster, 1),
                "naive_note": (
                    "the naive figure treats the committed split-half sd as if its "
                    "~half-archive draws were fresh clusters (no FPC), which is what "
                    "bare sqrt-m scaling gives; it understates m* by about half"
                ),
            }
            extrapolation["verdict"] = "CROSSOVER_ESTIMATED"

        # Sign question, stated explicitly for the short task.
        sign = ("delta > 0, CI excludes 0: a large enough fresh archive would flag "
                "this swap under the model"
                if delta > 0 and delta_ci[0] > 0 else
                "delta <= 0 with CI excluding 0: the swap fits the declared route "
                "at least as well as its own material; no m yields power above the "
                "false-alarm rate"
                if delta < 0 and delta_ci[1] < 0 else
                "CI straddles zero: the sign is unresolved at this cluster count; "
                "'never' is not asserted and neither is a crossover")

        results[task] = {
            "per_m": per_m,
            "paired_shift": {
                "delta": round(delta, 6),
                "ci95": delta_ci,
                "n_shared_clusters": len(shared),
                "sign_reading": sign,
            },
            "extrapolation": extrapolation,
        }
        print(f"  delta {delta:+.4f} CI {delta_ci}  S {s_hat:.3f}  "
              f"S_swap {s_swap:.3f}  z_emp {z_emp:.3f}")
        if isinstance(extrapolation.get("m_star"), dict):
            print(f"  m* rows: power0.5 {extrapolation['m_star']['power_0.5_rows']} "
                  f" power0.8 {extrapolation['m_star']['power_0.8_rows']}")
        else:
            print(f"  {extrapolation['verdict']}")

    doc = {
        "punchmark_schema": "angle_c_power_vs_m/v1",
        "seed": SEED,
        "far": FAR,
        "m_grid": list(M_GRID),
        "reconciliation": {"one_sample_json_stats_match": True},
        "measured_curve_caveat": (
            "power to flag subsamples of this swap archive against subsamples of "
            "this declared archive; inflates toward the full archive size by "
            "finite-population shrinkage and is not fresh-archive power"
        ),
        "tasks": results,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(doc))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/power_vs_m.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
