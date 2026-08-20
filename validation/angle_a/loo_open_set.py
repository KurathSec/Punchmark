#!/usr/bin/env python3
"""Does a competitor-free test flag the leave-one-out absorptions?

kt2.json records that with one route held out of the candidate set, that route's two
held-out archives are absorbed onto a remaining candidate 8 times out of 8, with no
signal that the true producer is missing. Review proposed the sharpening: apply the
one-sample fit statistic (the competitor-free formulation from Angle C) to each
absorbed archive UNDER its absorbing route. Consistent misses strengthen the
silent-absorption claim; rejections would show open-set rejection is partly feasible on
this channel and the closed-set conclusion would need refining.

The design trap, and its answer. The absorbing route's null must come from its own
within-window material (its fit archive), but the absorbed archives are held-out
re-minted content, and this project already measured that the false-alarm rate does not
transfer across content (KT2: same-route held-out cells reach 0.0598-0.1208 against a
declared 0.01). A flag on an absorbed archive could therefore be content transfer, not
open-set detection. The control that separates the two is MATCHED: the absorbing
route's own held-out archive on the same task, scored by the same detector against the
same null. Both archives answer the same re-minted items; the only difference is the
producer. A pooled baseline over all non-excluded archives is rejected because transfer
severity is cell-specific. Open-set signal requires the absorbed archive to sit
significantly below its matched control (one-sided 95% via the two cluster-bootstrap
SEs), not merely below the threshold.

Verdicts per absorbed archive:
  OPEN_SET_SIGNAL     flagged AND significantly below the matched control
  TRANSFER_CONFOUNDED flagged, but the matched control is comparable (UNDETERMINED:
                      the test cannot tell open-set detection from transfer noise)
  SILENT_ABSORPTION   not flagged
  ANOMALOUS_CONTROL   control flagged, absorbed archive not

Reconciliation before any new number: the LOO refit must reproduce kt2.json's
`leave_one_route_out` mapping exactly, and the absorbing route's score column must be
bit-identical to the shipped model's (chargram fits each (task, route) table from that
route's own counts alone, so excluding another route cannot change it -- asserted, not
assumed).

Zero API calls: reads the sibling checkout's archives and the shipped model only.

Usage:  .venv/bin/python validation/angle_a/loo_open_set.py [--source PATH] [--write]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.archive import read_archive  # noqa: E402
from punchmark.calibrate import (  # noqa: E402
    ScoredRow,
    ScoredSet,
    crossfit_scored,
    identify,
    split_half,
)
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import build_detector, fitted_from_params  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.modelfile import read_model  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402

CAL_DIR = ROOT / "calibration" / "spaghetti"
OUT = HERE / "derived" / "loo_one_sample.json"
SEED = 20260803
FAR = 0.01
N_NULL = 5000            # iterations; both halves kept, so 10,000 stats per null
B_ARCH = 1000            # cluster-bootstrap resamples per archive statistic

ROUTES = (
    "deepseek-ai/DeepSeek-V4-Flash",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
)
CANDIDATES = CandidateSet(routes=tuple(sorted(ROUTES)))
TASK_ALIAS = {
    "comprehend": "comprehend",
    "refactor_dev": "refactor_dev",
    "comprehend_test": "comprehend",
    "refactor_test": "refactor_dev",
}
GROUPS = [
    ("bench/out/ladder", "comprehend", "fit"),
    ("bench/out/g3", "refactor_dev", "fit"),
    ("bench/out/g3", "comprehend_test", "heldout"),
    ("bench/out/g3", "refactor_test", "heldout"),
]


def load_archives(source: Path) -> dict[str, list]:
    out: dict[str, list] = {"fit": [], "heldout": []}
    for rel_dir, task, role in GROUPS:
        for route in sorted(ROUTES):
            path = source / rel_dir / f"{task}__{route.replace('/', '-')}.jsonl.gz"
            rs = read_archive(path, CANDIDATES)
            rs = load_and_attach(rs, path, CAL_DIR / "sidecars")
            out[role].append(rs)
    return out


def fit_stat(rows, declared: str) -> float:
    return statistics.fmean(r.scores[declared] for r in rows)


def cluster_sums(ss: ScoredSet, declared: str) -> tuple[dict[str, float], dict[str, int]]:
    sums = {}
    counts = {}
    for name, rows in ss.clusters.items():
        sums[name] = sum(r.scores[declared] for r in rows)
        counts[name] = len(rows)
    return sums, counts


def archive_stat_ci(ss: ScoredSet, declared: str, tag: str) -> tuple[float, list[float], float]:
    """Whole-archive one-sample stat, its cluster-bootstrap 95% CI, and its SE."""
    sums, counts = cluster_sums(ss, declared)
    names = sorted(sums)
    point = sum(sums.values()) / sum(counts.values())
    boot = []
    for b in range(B_ARCH):
        rng = random.Random(derive_seed("a2-arch-boot", tag, ss.source_name, b, SEED))
        picks = [rng.choice(names) for _ in range(len(names))]
        boot.append(sum(sums[p] for p in picks) / sum(counts[p] for p in picks))
    boot.sort()
    ci = [boot[int(0.025 * B_ARCH)], boot[int(0.975 * B_ARCH) - 1]]
    se = statistics.stdev(boot)
    return point, [round(c, 6) for c in ci], se


def build_null(oof: ScoredSet, route: str, task: str) -> dict:
    """10,000 split-half one-sample stats of the route's fit archive OOF scores."""
    sums, counts = cluster_sums(oof, route)
    stats_ = []
    for i in range(N_NULL):
        rng = random.Random(derive_seed("a2-null", task, route, i, SEED))
        ha, hb = split_half(oof.clusters, rng)
        for half in (ha, hb):
            names = {r.cluster for r in half}
            stats_.append(sum(sums[n] for n in names) / sum(counts[n] for n in names))
    stats_.sort()
    thr = stats_[max(0, int(FAR * len(stats_)) - 1)]   # one_sample.py's conservative index
    return {
        "m_half_rows": round(statistics.fmean(len(h) for h in [ha, hb]), 1),
        "n_null": len(stats_),
        "threshold": round(thr, 6),
        "null_mean": round(statistics.fmean(stats_), 6),
        "null_sd": round(statistics.stdev(stats_), 6),
        "_thr": thr,
        "_mean": statistics.fmean(stats_),
        "_sd": statistics.stdev(stats_),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(ROOT.parent / "Spaghetti-Architect"))
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    source = Path(args.source)

    doc = read_model(CAL_DIR / "goldens" / "default.pmk-model.json")
    shipped = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)
    committed_loo = json.loads(
        (HERE / "derived" / "kt2.json").read_text(encoding="utf-8")
    )["leave_one_route_out"]

    archives = load_archives(source)
    detector = build_detector("chargram")

    # Nulls are per (route, task) and identical across LOO folds, because chargram's
    # per-route table depends only on that route's own counts and the crossfit fold
    # map is keyed on cluster names shared by all archives. Computed once from the
    # full four-route crossfit; the fold-level identity is asserted below.
    print("nulls: crossfit over the 8 fit archives, split-half one-sample stats")
    oof_all = {s.source_name: s
               for s in crossfit_scored(detector, archives["fit"], CANDIDATES, SEED)}
    nulls = {}
    for rs in archives["fit"]:
        s = oof_all[rs.source_name]
        nulls[(s.route, s.task)] = build_null(s, s.route, s.task)

    heldout_by = {(TASK_ALIAS[rs.task], rs.route): rs for rs in archives["heldout"]}
    shipped_cols_checked = 0
    folds_out = {}
    summary = {"OPEN_SET_SIGNAL": 0, "TRANSFER_CONFOUNDED": 0,
               "SILENT_ABSORPTION": 0, "ANOMALOUS_CONTROL": 0}

    for excluded in sorted(ROUTES):
        remaining = CandidateSet(
            routes=tuple(r for r in CANDIDATES.routes if r != excluded)
        )
        train = [rs for rs in archives["fit"] if rs.route != excluded]
        fitted = detector.fit(train, remaining, SEED)
        print(f"\nfold: excluded {excluded}")

        # Fold-level null identity spot check (one route, one task).
        probe_route = remaining.routes[0]
        oof_fold = {s.source_name: s
                    for s in crossfit_scored(detector, train, remaining, SEED)}
        for rs in train:
            if rs.route != probe_route:
                continue
            a = oof_fold[rs.source_name]
            b = oof_all[rs.source_name]
            for ra, rb in zip(a.rows, b.rows, strict=True):
                if ra.scores[probe_route] != rb.scores[probe_route]:
                    raise SystemExit("fold-level OOF column differs from shared null")
        absorbed_out = []
        context_out = []
        for rs in archives["heldout"]:
            task = TASK_ALIAS[rs.task]
            rows = rs.valid_rows
            scored = fitted.score_rows(rows, task)
            ss = ScoredSet(
                route=rs.route, task=task, source_name=rs.source_name,
                rows=tuple(ScoredRow(key=r.item_key, cluster=r.cluster, scores=sc)
                           for r, sc in zip(rows, scored, strict=True)),
            )
            if rs.route == excluded:
                mapped_to = identify(ss.rows, remaining.routes)
                want = next(
                    e["mapped_to"]
                    for e in committed_loo[excluded]["excluded_route_maps_to"]
                    if e["archive"] == rs.source_name
                )
                if mapped_to != want:
                    raise SystemExit(
                        f"LOO reconciliation failed: {rs.source_name} maps to "
                        f"{mapped_to}, kt2.json says {want}"
                    )
                # Consistency: the absorbing column must equal the shipped model's.
                ship_scored = shipped.score_rows(rows, task)
                for sc, sh in zip(scored, ship_scored, strict=True):
                    if sc[mapped_to] != sh[mapped_to]:
                        raise SystemExit("absorbing column differs from shipped model")
                shipped_cols_checked += 1

                null = nulls[(mapped_to, task)]
                stat, ci, se = archive_stat_ci(ss, mapped_to, f"abs-{excluded}")
                ctrl_rs = heldout_by[(task, mapped_to)]
                ctrl_rows = ctrl_rs.valid_rows
                ctrl_scored = fitted.score_rows(ctrl_rows, task)
                ctrl = ScoredSet(
                    route=mapped_to, task=task, source_name=ctrl_rs.source_name,
                    rows=tuple(
                        ScoredRow(key=r.item_key, cluster=r.cluster, scores=sc)
                        for r, sc in zip(ctrl_rows, ctrl_scored, strict=True)
                    ),
                )
                cstat, cci, cse = archive_stat_ci(ctrl, mapped_to, f"ctl-{excluded}")

                z = (stat - null["_mean"]) / null["_sd"]
                cz = (cstat - null["_mean"]) / null["_sd"]
                flagged = stat < null["_thr"]
                cflagged = cstat < null["_thr"]
                gap_z = cz - z          # positive: absorbed sits below its control
                gap_se = ((se ** 2 + cse ** 2) ** 0.5) / null["_sd"]
                significant = gap_z > 1.645 * gap_se
                if flagged and cflagged and not significant:
                    verdict = "TRANSFER_CONFOUNDED"
                elif flagged and significant:
                    verdict = "OPEN_SET_SIGNAL"
                elif flagged:
                    verdict = "TRANSFER_CONFOUNDED"
                elif cflagged:
                    verdict = "ANOMALOUS_CONTROL"
                else:
                    verdict = "SILENT_ABSORPTION"
                summary[verdict] += 1
                print(f"  {rs.source_name}")
                print(f"    absorbed onto {mapped_to}: stat {stat:+.4f} (z {z:+.2f}) "
                      f"{'FLAGGED' if flagged else 'not flagged'};  control "
                      f"{cstat:+.4f} (z {cz:+.2f}) "
                      f"{'FLAGGED' if cflagged else 'not flagged'};  "
                      f"gap_z {gap_z:+.2f}  ->  {verdict}")
                absorbed_out.append({
                    "archive": rs.source_name,
                    "absorbing_route": mapped_to,
                    "stat": round(stat, 6),
                    "z": round(z, 4),
                    "margin_over_threshold": round(stat - null["_thr"], 6),
                    "flagged_at_far": flagged,
                    "stat_ci95_cluster_boot": ci,
                    "matched_control": {
                        "archive": ctrl_rs.source_name,
                        "stat": round(cstat, 6),
                        "z": round(cz, 4),
                        "flagged_at_far": cflagged,
                        "stat_ci95_cluster_boot": cci,
                    },
                    "gap_z": round(gap_z, 4),
                    "gap_significant_1sided_95": significant,
                    "verdict": verdict,
                })
            else:
                null = nulls[(rs.route, task)]
                stat = fit_stat(ss.rows, rs.route)
                context_out.append({
                    "archive": rs.source_name,
                    "own_route": rs.route,
                    "z": round((stat - null["_mean"]) / null["_sd"], 4),
                    "flagged_at_far": stat < null["_thr"],
                })
        folds_out[excluded] = {
            "absorbed": absorbed_out,
            "context_controls_own_route": context_out,
        }

    body = {
        "punchmark_schema": "angle_a_loo_one_sample/v1",
        "seed": SEED,
        "far": FAR,
        "statistic": (
            "mean length-normalised log-likelihood under the ABSORBING route only; "
            "no competitor set enters the statistic (the Angle C one-sample "
            "formulation applied to the LOO absorptions)"
        ),
        "null": (
            "10,000 split-half one-sample stats of the absorbing route's FIT archive "
            "out-of-fold scores; conservative 1% quantile. The fit archive is the "
            "largest within-window same-route material a route has, and its halves "
            "(~25 clusters) are smaller than the judged archives (74 clusters), "
            "which widens the null and is conservative for absolute flags; the "
            "decision rule is control-relative, where the null scale cancels"
        ),
        "nulls": {
            f"{task}|{route}": {k: v for k, v in n.items() if not k.startswith("_")}
            for (route, task), n in sorted(nulls.items())
        },
        "reconciliation": {
            "loo_mapping_matches_kt2_json": True,
            "absorbing_columns_identical_to_shipped_model": shipped_cols_checked,
        },
        "folds": folds_out,
        "summary": summary,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(body))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/loo_one_sample.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
