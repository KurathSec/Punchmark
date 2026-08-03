#!/usr/bin/env python3
"""Angle A: calibrate on the committed dev archives, validate on the held-out test
archives. Zero API calls; everything derives from the pinned corpus.

Experiments (each writes a canonical JSON artifact into derived/):

E0  census        -- the archives must match the verified ground truth exactly
E1  score tables  -- shipped CANON model over all 16 archives (+ RAW/ABL refits)
E2  KT1           -- held-out whole-set identification (canonical 8 + clustered
                     subsample population at m=150 with cluster-bootstrap CI;
                     tier-stratified)
E3  KT2           -- the false-alarm promise (canonical split-half pair rulings +
                     measured within-window flag rate vs the declared 1%), the
                     leave-one-route-out diagnostic, and the file-order
                     null-integrity check
E4  power         -- held-out seeded-substitution power and rho* at the shipped
                     thresholds
E6  KT3           -- formatting ablation: RAW/CANON/ABL identification, recorded
                     binary form plus the per-pair channel margins
E7  probe         -- the frozen 150-row probe subset and its manifest
E8  transfer      -- ablation-arm archives (k=1, different prompt condition,
                     ~2 weeks later): identification-only diagnostic, declared
                     confounded; NO verdict vocabulary
E9  certificates  -- canonical held-out rulings + certificates + gate snapshot

Kill-test wiring (deviations from the recorded wording are declared in
FINDING.md): KT1 passes iff canonical 8/8 AND pooled subsample accuracy at m=150
>= 0.95 with cluster-bootstrap CI lower bound >= 0.90. KT2 fires iff the measured
within-window flag rate significantly exceeds the declared 1% (cluster-bootstrap
lower bound over archives > 0.01) or the null cannot be estimated; canonical
flags are reported and investigated, never auto-kill. KT3's recorded binary form
fires iff RAW accuracy > 0.95 AND ABL accuracy < 0.50; independently, the
premise-void verdict requires the ABL (content) channel at chance for all pairs.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.archive import read_archive  # noqa: E402
from punchmark.calibrate import (  # noqa: E402
    ScoredRow,
    ScoredSet,
    cluster_subset,
    identify,
    lookup_threshold,
    split_half,
    t_statistic,
)
from punchmark.canonical import canonical_json, derive_seed, write_text_deterministic  # noqa: E402
from punchmark.certify import certificate_from_ruling  # noqa: E402
from punchmark.corpus import read_manifest  # noqa: E402
from punchmark.detector import build_detector, fitted_from_params  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.modelfile import read_model  # noqa: E402
from punchmark.rulings import append, ruling_body, verify  # noqa: E402
from punchmark.score import RulePolicy, rule  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402
from punchmark.spec import spec_version  # noqa: E402

CAL_DIR = ROOT / "calibration" / "spaghetti"
DERIVED = HERE / "derived"
SEED = 20260803
FAR = 0.01
M_PROBE = 150

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

# Verified ground truth (plan "Pre-measurements"); E0 aborts on any mismatch.
EXPECTED_TOTAL_ROWS = 26_880
EXPECTED_TOTAL_COMPLETIONS = 214_856
EXPECTED_TOTAL_STUBS = 23
EXPECTED_MISTRAL_CT_STUBS = 13


def emit(name: str, body: dict) -> None:
    write_text_deterministic(DERIVED / name, canonical_json(body))
    print(f"  wrote derived/{name}")


def load_archives(source: Path) -> dict[str, list]:
    out: dict[str, list] = {"fit": [], "heldout": []}
    for rel_dir, task, role in GROUPS:
        for route in sorted(ROUTES):
            path = source / rel_dir / f"{task}__{route.replace('/', '-')}.jsonl.gz"
            rs = read_archive(path, CANDIDATES)
            rs = load_and_attach(rs, path, CAL_DIR / "sidecars")
            out[role].append(rs)
    return out


def e0_census(archives: dict[str, list]) -> None:
    print("E0 census")
    all_sets = archives["fit"] + archives["heldout"]
    total_rows = sum(len(rs.rows) for rs in all_sets)
    total_completions = sum(
        len(r.raw_outputs) for rs in all_sets for r in rs.valid_rows
    )
    total_stubs = sum(rs.n_stub_rows for rs in all_sets)
    mistral_ct = next(
        rs for rs in all_sets
        if rs.task == "comprehend_test" and rs.route.startswith("mistralai/")
    )
    ladder_tiers = [
        r.tier for rs in all_sets if rs.task == "comprehend" for r in rs.valid_rows
    ]
    # draw degeneracy and the format-cluster identity floor (first draw, dev comprehend)
    deg: dict[str, dict[str, float]] = {}
    for rs in all_sets:
        distinct = [len(set(r.raw_outputs)) for r in rs.valid_rows]
        all_same = sum(1 for r in rs.valid_rows if len(set(r.raw_outputs)) == 1)
        deg[rs.source_name] = {
            "mean_distinct_draws": round(statistics.fmean(distinct), 4),
            "all_draws_identical_share": round(all_same / len(distinct), 4),
        }
    dev_comp = {
        rs.route: {r.item_key: r.raw_outputs[0] for r in rs.valid_rows}
        for rs in archives["fit"]
        if rs.task == "comprehend"
    }
    ds = dev_comp["deepseek-ai/DeepSeek-V4-Flash"]
    l70 = dev_comp["meta-llama/Llama-3.3-70B-Instruct-Turbo"]
    shared = sorted(set(ds) & set(l70))
    identical_raw = sum(1 for k in shared if ds[k] == l70[k])
    identical_ws = sum(
        1 for k in shared if " ".join(ds[k].split()) == " ".join(l70[k].split())
    )
    body = {
        "total_rows": total_rows,
        "total_completions": total_completions,
        "total_stub_rows": total_stubs,
        "mistral_comprehend_test_stubs": mistral_ct.n_stub_rows,
        "ladder_rows_carry_tier": any(t is not None for t in ladder_tiers),
        "draw_degeneracy": deg,
        "info_floor_deepseek_l70b_comprehend_dev": {
            "n_shared_items": len(shared),
            "byte_identical_first_draw": identical_raw,
            "ws_normalized_identical_first_draw": identical_ws,
        },
    }
    emit("census.json", body)
    checks = [
        (total_rows == EXPECTED_TOTAL_ROWS, f"rows {total_rows}"),
        (total_completions == EXPECTED_TOTAL_COMPLETIONS, f"completions {total_completions}"),
        (total_stubs == EXPECTED_TOTAL_STUBS, f"stubs {total_stubs}"),
        (mistral_ct.n_stub_rows == EXPECTED_MISTRAL_CT_STUBS, "mistral stubs"),
        (not body["ladder_rows_carry_tier"], "ladder tier absence"),
    ]
    failed = [msg for ok, msg in checks if not ok]
    if failed:
        raise SystemExit(f"E0 census mismatch against verified ground truth: {failed}")


def score_all(fitted, archives: dict[str, list]) -> dict[str, ScoredSet]:
    """source_name -> ScoredSet under the model's task (aliased for heldout)."""
    tables: dict[str, ScoredSet] = {}
    for role in ("fit", "heldout"):
        for rs in archives[role]:
            model_task = TASK_ALIAS[rs.task]
            rows = rs.valid_rows
            scored = fitted.score_rows(rows, model_task)
            tables[rs.source_name] = ScoredSet(
                route=rs.route,
                task=model_task,
                source_name=rs.source_name,
                rows=tuple(
                    ScoredRow(key=r.item_key, cluster=r.cluster, scores=s)
                    for r, s in zip(rows, scored, strict=True)
                ),
            )
    return tables


def _subsample_accuracy(
    ss: ScoredSet, m: int, n_draws: int, seed_tag: str,
    clusters: dict[str, tuple[ScoredRow, ...]] | None = None,
) -> float:
    clusters = clusters if clusters is not None else ss.clusters
    correct = 0
    for i in range(n_draws):
        rng = random.Random(derive_seed("kt1-subsample", seed_tag, ss.source_name, m, i, SEED))
        subset = cluster_subset(clusters, m, rng)
        if identify(subset, CANDIDATES.routes) == ss.route:
            correct += 1
    return correct / n_draws


def e2_kt1(tables: dict[str, ScoredSet], archives: dict[str, list]) -> dict:
    print("E2 KT1 held-out identification")
    heldout = [tables[rs.source_name] for rs in archives["heldout"]]
    canonical = {
        ss.source_name: {
            "declared": ss.route,
            "identified": identify(ss.rows, CANDIDATES.routes),
        }
        for ss in heldout
    }
    n_correct = sum(1 for v in canonical.values() if v["declared"] == v["identified"])
    # exact one-sided 95% lower bound for x successes of n: for x=n it is alpha^(1/n)
    exact_lower = round(0.05 ** (1 / len(canonical)), 4) if n_correct == len(canonical) else None

    per_archive = {
        ss.source_name: round(_subsample_accuracy(ss, M_PROBE, 2000, "main"), 4)
        for ss in heldout
    }
    pooled = round(statistics.fmean(per_archive.values()), 4)

    # cluster bootstrap over each archive's clusters; B=200, 50 subsets each
    boot: list[float] = []
    for b in range(200):
        accs = []
        for ss in heldout:
            rng = random.Random(derive_seed("kt1-boot", ss.source_name, b, SEED))
            names = sorted(ss.clusters)
            resampled = [rng.choice(names) for _ in names]
            clusters = {}
            for j, name in enumerate(resampled):
                clusters[f"{name}#{j}"] = ss.clusters[name]
            accs.append(_subsample_accuracy(ss, M_PROBE, 50, f"boot{b}", clusters))
        boot.append(statistics.fmean(accs))
    boot.sort()
    ci_lower = round(boot[int(0.05 * len(boot))], 4)

    # tier stratification: B/C clusters are the only structurally unseen families
    tier_bc: dict[str, float | None] = {}
    for rs in archives["heldout"]:
        ss = tables[rs.source_name]
        bc_clusters = {
            c: rows for c, rows in ss.clusters.items()
            if c.startswith(("tierB_", "tierC_"))
        }
        n_rows = sum(len(v) for v in bc_clusters.values())
        if n_rows >= M_PROBE:
            tier_bc[rs.source_name] = round(
                _subsample_accuracy(ss, M_PROBE, 500, "tierbc", bc_clusters), 4
            )
        else:
            tier_bc[rs.source_name] = None
    kt1_pass = (
        n_correct == len(canonical) and pooled >= 0.95 and ci_lower >= 0.90
    )
    body = {
        "canonical_whole_archive": canonical,
        "canonical_correct": f"{n_correct}/{len(canonical)}",
        "canonical_exact_lower_bound_95": exact_lower,
        "subsample_accuracy_m150": per_archive,
        "subsample_pooled": pooled,
        "cluster_bootstrap_ci_lower_5pct": ci_lower,
        "tier_bc_only_accuracy_m150": tier_bc,
        "tier_bc_note": (
            "tier B/C are the only structurally unseen families (24 clusters, 360 "
            "rows per archive); suggestive, not significant, at this cluster count"
        ),
        "kt1_threshold": "canonical 8/8 AND pooled >= 0.95 AND CI lower >= 0.90",
        "kt1_pass": kt1_pass,
    }
    emit("kt1.json", body)
    return body


def e3_kt2(doc, tables: dict[str, ScoredSet], archives: dict[str, list]) -> dict:
    print("E3 KT2 false-alarm promise + LOO + null integrity")
    all_sets = [tables[rs.source_name] for rs in archives["fit"] + archives["heldout"]]

    def flagged(rows) -> tuple[bool, float | None, float | None]:
        op = lookup_threshold(
            doc.operating_points, rows_task, rows_route, FAR, len(rows)
        )
        if op is None:
            return False, None, None
        t = t_statistic(rows, rows_route, CANDIDATES.routes)
        return t < op.threshold, t, op.threshold

    canonical_pairs = []
    n_flag_canonical = 0
    measured = {}
    for ss in all_sets:
        rows_task, rows_route = ss.task, ss.route
        clusters = ss.clusters
        rng = random.Random(derive_seed("kt2-canonical", ss.source_name, SEED))
        half_a, half_b = split_half(clusters, rng)
        for label, half in (("a", half_a), ("b", half_b)):
            is_flagged, t, thr = flagged(half)
            n_flag_canonical += int(is_flagged)
            canonical_pairs.append(
                {
                    "archive": ss.source_name,
                    "half": label,
                    "n_rows": len(half),
                    "t": None if t is None else round(t, 6),
                    "threshold": None if thr is None else round(thr, 6),
                    "flagged": is_flagged,
                }
            )
        flags = 0
        n_splits = 2500
        for i in range(n_splits):
            rng = random.Random(derive_seed("kt2-measured", ss.source_name, i, SEED))
            ha, hb = split_half(clusters, rng)
            fa, _, _ = flagged(ha)
            fb, _, _ = flagged(hb)
            flags += int(fa or fb)
        measured[ss.source_name] = flags / n_splits

    pooled_rate = statistics.fmean(measured.values())

    def stratum_stats(names: list[str], tag: str) -> dict:
        rates = [measured[n] for n in names]
        boot = []
        for b in range(2000):
            rng = random.Random(derive_seed("kt2-boot", tag, b, SEED))
            boot.append(statistics.fmean(rng.choices(rates, k=len(rates))))
        boot.sort()
        return {
            "archives": len(rates),
            "pooled_rate": round(statistics.fmean(rates), 4),
            "bootstrap_lower_5pct": round(boot[int(0.05 * len(boot))], 4),
            "bootstrap_upper_95pct": round(boot[int(0.95 * len(boot)) - 1], 4),
        }

    # Two strata, deliberately separate. The RECORDED KT2 is about same-route pairs
    # inside one window of the calibration content: the fit stratum. The heldout
    # stratum applies dev-calibrated thresholds to RE-MINTED content under a
    # declared task alias -- a transfer question the recorded test never posed,
    # reported as its own finding rather than diluted into the kill criterion.
    fit_names = [rs.source_name for rs in archives["fit"]]
    heldout_names = [rs.source_name for rs in archives["heldout"]]
    fit_stats = stratum_stats(fit_names, "fit")
    heldout_stats = stratum_stats(heldout_names, "heldout")
    kt2_fires = fit_stats["bootstrap_lower_5pct"] > FAR

    # leave-one-route-out: diagnostic only, n=4 sits at the LOO floor (declared)
    loo = {}
    for excluded in sorted(ROUTES):
        remaining = CandidateSet(
            routes=tuple(r for r in CANDIDATES.routes if r != excluded)
        )
        train = [
            rs for rs in archives["fit"] if rs.route != excluded
        ]
        fitted3 = build_detector("chargram").fit(train, remaining, SEED)
        ident_ok = 0
        ident_n = 0
        open_set = []
        for rs in archives["heldout"]:
            model_task = TASK_ALIAS[rs.task]
            rows = rs.valid_rows
            scored = tuple(
                ScoredRow(key=r.item_key, cluster=r.cluster, scores=s)
                for r, s in zip(rows, fitted3.score_rows(rows, model_task), strict=True)
            )
            if rs.route == excluded:
                # closed-set: the excluded producer maps to its nearest member
                open_set.append(
                    {
                        "archive": rs.source_name,
                        "mapped_to": identify(scored, remaining.routes),
                    }
                )
            else:
                ident_n += 1
                ident_ok += int(identify(scored, remaining.routes) == rs.route)
        loo[excluded] = {
            "three_way_identification": f"{ident_ok}/{ident_n}",
            "excluded_route_maps_to": open_set,
        }

    # null-integrity: file-order halves of the 4-hour refactor_test window
    integrity = {}
    for rs in archives["heldout"]:
        if rs.task != "refactor_test":
            continue
        ss = tables[rs.source_name]
        rows_task, rows_route = ss.task, ss.route
        mid = len(ss.rows) // 2
        first, second = ss.rows[:mid], ss.rows[mid:]
        fa, ta, tha = flagged(first)
        fb, tb, thb = flagged(second)
        integrity[ss.source_name] = {
            "first_half": {"t": round(ta, 6) if ta is not None else None, "flagged": fa},
            "second_half": {"t": round(tb, 6) if tb is not None else None, "flagged": fb},
            "note": (
                "file-order proxy for collection order inside the 3h58m window; "
                "a check on null integrity, not a verdict (PMK-CAL-003)"
            ),
        }

    body = {
        "canonical_pairs": canonical_pairs,
        "canonical_flags": n_flag_canonical,
        "canonical_note": (
            "any canonical flag is investigated and declared, not auto-kill: at a "
            "true 1% rate, >=1 flag among 32 pairs occurs with p~0.27 (the recorded "
            "any-single-pair wording is statistically incoherent under resampling "
            "and is rewired here, declared in FINDING.md)"
        ),
        "measured_pair_flag_rate": {k: round(v, 4) for k, v in measured.items()},
        "pooled_rate_all_16": round(pooled_rate, 4),
        "stratum_fit_within_calibration_content": fit_stats,
        "stratum_heldout_reminted_content": heldout_stats,
        "declared_far": FAR,
        "kt2_threshold": (
            "fires iff the FIT stratum's bootstrap lower bound > declared far "
            "(the recorded within-window promise); the heldout stratum is the "
            "cross-content transfer finding, reported separately"
        ),
        "kt2_fires": kt2_fires,
        "transfer_finding": {
            "far_transfers_to_reminted_content": heldout_stats["bootstrap_lower_5pct"] <= FAR,
            "note": (
                "dev-calibrated per-route thresholds applied to re-minted held-out "
                "content inflate the within-window flag rate far above the declared "
                "1% for some (route, task) cells; a certificate at the declared far "
                "is trustworthy over the calibration content family, and scoring "
                "other content with these thresholds weakens the false-alarm "
                "guarantee to the rates measured here"
            ),
        },
        "leave_one_route_out": loo,
        "loo_note": "diagnostic only: route unit n=4 sits exactly at the LOO floor; no CIs",
        "null_integrity_file_order": integrity,
    }
    emit("kt2.json", body)
    return body


def e4_power_heldout(doc, tables: dict[str, ScoredSet], archives: dict[str, list]) -> dict:
    print("E4 held-out seeded-substitution power")
    heldout = [tables[rs.source_name] for rs in archives["heldout"]]
    by_task_route = {(ss.task, ss.route): ss for ss in heldout}
    rho_grid = (0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
    n_splice = 300
    results = []
    for (task, declared), base in sorted(by_task_route.items()):
        n_rows = len(base.rows)
        op = lookup_threshold(doc.operating_points, task, declared, FAR, n_rows)
        if op is None:
            continue
        for substitute in sorted(ROUTES):
            if substitute == declared:
                continue
            donor = by_task_route[(task, substitute)]
            donor_by_key = {r.key: r for r in donor.rows}
            rho_min = None
            powers = {}
            for rho in rho_grid:
                flags = 0
                for i in range(n_splice):
                    rng = random.Random(
                        derive_seed("heldout-splice", task, declared, substitute,
                                    f"rho={rho}", i, SEED)
                    )
                    subset = cluster_subset(base.clusters, op.m, rng)
                    if rho > 0:
                        names = sorted({r.cluster for r in subset})
                        rng.shuffle(names)
                        target = rho * len(subset)
                        swapped: set[str] = set()
                        n_sw = 0
                        for nm in names:
                            if n_sw >= target:
                                break
                            swapped.add(nm)
                            n_sw += sum(1 for r in subset if r.cluster == nm)
                        subset = tuple(
                            donor_by_key.get(r.key, r) if r.cluster in swapped else r
                            for r in subset
                        )
                    t = t_statistic(subset, declared, CANDIDATES.routes)
                    flags += int(t < op.threshold)
                power = flags / n_splice
                powers[str(rho)] = round(power, 4)
                if rho > 0 and rho_min is None and power >= 0.8:
                    rho_min = rho
            results.append(
                {
                    "task": task,
                    "declared": declared,
                    "substitute": substitute,
                    "m": op.m,
                    "far": FAR,
                    "power_by_rho": powers,
                    "rho_zero_selfcheck_leq_far": powers["0.0"] <= FAR + 0.02,
                    "rho_min_at_power_0.8": rho_min,
                }
            )
    body = {
        "note": (
            "held-out generalization of the power table: splices of heldout score "
            "rows at the SHIPPED dev-calibrated thresholds; seeded fidelity to real "
            "vendor changes cannot be validated and stands as a bound (PMK-POW-004)"
        ),
        "results": results,
    }
    emit("power_heldout.json", body)
    return body


def e6_kt3(archives: dict[str, list]) -> dict:
    print("E6 KT3 formatting ablation (RAW / CANON / ABL)")
    out = {}
    margins = {}
    for view in ("RAW@1", "CANON@1", "ABL@1"):
        fitted = build_detector("chargram", view=view).fit(
            archives["fit"], CANDIDATES, SEED
        )
        correct = 0
        per_pair_t: dict[str, list[float]] = {}
        accs = {}
        for rs in archives["heldout"]:
            model_task = TASK_ALIAS[rs.task]
            rows = rs.valid_rows
            scored = tuple(
                ScoredRow(key=r.item_key, cluster=r.cluster, scores=s)
                for r, s in zip(rows, fitted.score_rows(rows, model_task), strict=True)
            )
            ss = ScoredSet(route=rs.route, task=model_task,
                           source_name=rs.source_name, rows=scored)
            ident = identify(scored, CANDIDATES.routes)
            correct += int(ident == rs.route)
            accs[rs.source_name] = round(_subsample_accuracy(ss, M_PROBE, 500, f"kt3-{view}"), 4)
            for alt in CANDIDATES.routes:
                if alt == rs.route:
                    continue
                mean_own = statistics.fmean(r.scores[rs.route] for r in scored)
                mean_alt = statistics.fmean(r.scores[alt] for r in scored)
                per_pair_t.setdefault(f"{model_task}:{rs.route}|{alt}", []).append(
                    mean_own - mean_alt
                )
        out[view] = {
            "canonical_correct": f"{correct}/{len(archives['heldout'])}",
            "subsample_accuracy_m150": accs,
            "pooled_m150": round(statistics.fmean(accs.values()), 4),
        }
        margins[view] = {
            pair: round(statistics.fmean(vals), 6) for pair, vals in sorted(per_pair_t.items())
        }
    raw_acc = out["RAW@1"]["pooled_m150"]
    abl_acc = out["ABL@1"]["pooled_m150"]
    recorded_fires = raw_acc > 0.95 and abl_acc < 0.50
    abl_at_chance_all_pairs = all(m <= 0.0 for m in margins["ABL@1"].values())
    body = {
        "per_view": out,
        "per_pair_mean_margin": margins,
        "recorded_form": {
            "raw_pooled_m150": raw_acc,
            "abl_pooled_m150": abl_acc,
            "fires_iff": "raw > 0.95 AND abl < 0.50",
            "fires": recorded_fires,
        },
        "content_channel_at_chance_all_pairs": abl_at_chance_all_pairs,
        "premise_void": recorded_fires and abl_at_chance_all_pairs,
        "note": (
            "channels approximated by the shipped views: ABL strips fences, case and "
            "whitespace and truncates to 200 chars (content-ish); CANON strips the "
            "fragile outer-fence/whitespace channel but keeps case; RAW keeps "
            "everything (PMK-DET-004)"
        ),
    }
    emit("kt3.json", body)
    return body


def e7_probe(doc, archives: dict[str, list]) -> dict:
    print("E7 frozen 150-row probe selection (dev archives only)")
    for rs in archives["fit"]:
        if "_test__" in rs.source_name:
            raise SystemExit("probe selector saw a test archive; refusing")
    # utility from the shipped model's OWN dev scores (full-fit; the probe serves
    # future re-runs, not held-out evaluation)
    fitted = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)
    by_task: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    meta: dict[str, dict[str, tuple[str, str, str]]] = {}
    for rs in archives["fit"]:
        rows = rs.valid_rows
        scored = fitted.score_rows(rows, rs.task)
        for r, s in zip(rows, scored, strict=True):
            by_task.setdefault(rs.task, {}).setdefault(r.item_key, {})[rs.route] = s
            meta.setdefault(rs.task, {})[r.item_key] = (r.sample, r.profile, r.language)
    selected: dict[str, list[str]] = {}
    for task, items in sorted(by_task.items()):
        utilities: list[tuple[float, str]] = []
        for key, per_route in items.items():
            if len(per_route) != len(ROUTES):
                continue
            u = min(
                per_route[r][r] - per_route[r][alt]
                for r in per_route
                for alt in per_route[r]
                if alt != r
            )
            utilities.append((u, key))
        utilities.sort(reverse=True)
        picked: list[str] = []
        per_sample: Counter[str] = Counter()
        per_language: Counter[str] = Counter()
        per_profile: Counter[str] = Counter()
        for _u, key in utilities:
            sample, profile, language = meta[task][key]
            if per_sample[sample] >= 2:
                continue
            picked.append(key)
            per_sample[sample] += 1
            per_language[language] += 1
            per_profile[profile] += 1
            if len(picked) == 75:
                break
        selected[task] = sorted(picked)
    body = {
        "selector_version": "probe/v1",
        "seed": SEED,
        "model_id": doc.model_id,
        "criteria": (
            "worst-ordered-pair margin utility on the fit archives, greedy under "
            "caps (<=2 rows per base sample), 75 rows per task; dev archives only, "
            "enforced by refusal"
        ),
        "items": selected,
        "power_note": (
            "expected probe power is the shipped model's m=150 power table; the "
            "hardest pairs are marginal at this size by design and a probe run "
            "inherits that limit"
        ),
    }
    emit("probe_manifest.json", body)
    return body


def e8_transfer(doc, source: Path) -> dict:
    print("E8 ablation-arm transfer probe (identification only, declared confounded)")
    fitted = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)
    results = {}
    abl_dir = source / "bench" / "out" / "ablation"
    task_map = {"comprehend_unannotated": "comprehend", "refactor_unannotated": "refactor_dev"}
    for path in sorted(abl_dir.glob("*.jsonl.gz")):
        rs = read_archive(path, CANDIDATES)
        model_task = task_map.get(rs.task)
        if model_task is None:
            continue
        rows = rs.valid_rows
        scored = tuple(
            ScoredRow(key=r.item_key, cluster=r.cluster, scores=s)
            for r, s in zip(rows, fitted.score_rows(rows, model_task), strict=True)
        )
        results[rs.source_name] = {
            "declared_label": rs.route,
            "identified": identify(scored, CANDIDATES.routes),
            "k": 1,
        }
    n_ok = sum(1 for v in results.values() if v["declared_label"] == v["identified"])
    body = {
        "results": results,
        "correct": f"{n_ok}/{len(results)}",
        "confound_declared": (
            "these archives were collected ~2 weeks after the calibration corpus "
            "under a DIFFERENT prompt condition (unannotated), with serving-side "
            "drift uncontrolled; identification transfer only -- verdict vocabulary "
            "is forbidden for this arm and it is excluded from the calibration "
            "corpus and all false-alarm calibration"
        ),
    }
    emit("ablation_probe.json", body)
    return body


def e9_certificates(doc, archives: dict[str, list]) -> dict:
    print("E9 canonical rulings + certificates")
    store = DERIVED / "rulings.jsonl"
    if store.exists():
        store.unlink()
    lines = []
    for rs in archives["heldout"]:
        ruling = rule(
            doc, rs, RulePolicy(far=FAR), spec_version(), scored_as=TASK_ALIAS[rs.task]
        )
        append(store, ruling)
        cert = certificate_from_ruling(ruling_body(ruling))
        lines.append(cert.line)
    verify(store)
    write_text_deterministic(DERIVED / "certificates.txt", "\n".join(lines) + "\n")
    print(f"  wrote derived/rulings.jsonl ({len(lines)} rulings) and certificates.txt")
    return {"n_rulings": len(lines)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="/home/kureist/Spaghetti-Architect")
    args = parser.parse_args()
    source = Path(args.source)
    DERIVED.mkdir(parents=True, exist_ok=True)

    manifest = read_manifest(CAL_DIR)
    doc = read_model(CAL_DIR / "goldens" / "default.pmk-model.json")
    if doc.calibration_sha256 != manifest.corpus_sha256:
        raise SystemExit("model and manifest disagree; rebuild the calibration")

    archives = load_archives(source)
    e0_census(archives)
    print("E1 score tables (shipped CANON model over all 16 archives)")
    fitted = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)
    tables = score_all(fitted, archives)
    kt1 = e2_kt1(tables, archives)
    kt2 = e3_kt2(doc, tables, archives)
    e4_power_heldout(doc, tables, archives)
    kt3 = e6_kt3(archives)
    e7_probe(doc, archives)
    e8_transfer(doc, source)
    e9_certificates(doc, archives)

    readout = [
        f"Angle A readout (model {doc.model_id}, corpus {manifest.corpus_sha256}, "
        f"spec {spec_version()})",
        f"KT1: canonical {kt1['canonical_correct']}, subsample@150 {kt1['subsample_pooled']}, "
        f"CI lower {kt1['cluster_bootstrap_ci_lower_5pct']} -> "
        f"{'PASS' if kt1['kt1_pass'] else 'KILL FIRES'}",
        f"KT2 (recorded, fit stratum): rate "
        f"{kt2['stratum_fit_within_calibration_content']['pooled_rate']} "
        f"(declared {FAR}), canonical flags {kt2['canonical_flags']}/32 -> "
        f"{'FIRES' if kt2['kt2_fires'] else 'HOLDS'}",
        f"KT2 transfer (heldout stratum, re-minted content): rate "
        f"{kt2['stratum_heldout_reminted_content']['pooled_rate']} "
        f"(lower bound {kt2['stratum_heldout_reminted_content']['bootstrap_lower_5pct']}) -> "
        f"{'DOES NOT TRANSFER' if not kt2['transfer_finding']['far_transfers_to_reminted_content'] else 'transfers'}",
        f"KT3: recorded form fires={kt3['recorded_form']['fires']}, "
        f"premise_void={kt3['premise_void']} "
        f"(RAW {kt3['recorded_form']['raw_pooled_m150']}, "
        f"ABL {kt3['recorded_form']['abl_pooled_m150']})",
    ]
    write_text_deterministic(DERIVED / "readout.txt", "\n".join(readout) + "\n")
    print()
    for line in readout:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
