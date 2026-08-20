#!/usr/bin/env python3
"""Is "at chance on the short task" a property of the channel, or of 3-5-grams?

The paper's channel bound says the two providers are indistinguishable "to this
detector" on ~59-character completions. Review pressed on the qualifier: the
byte-identity floor covers only part of the corpus, so inseparability on the remainder
may reflect the weakness of the 3-5-gram feature family rather than a limit of the
text. This probe runs two DELIBERATELY stronger feature families over the identical
pipeline and asks whether either moves the short task off chance:

  hi-gram : character n-grams of order {6, 7, 8}, same crc32 bucketing, 2^18 buckets
  word    : whitespace-token 1-2-grams, same bucketing

Both are implemented locally in this script rather than added to src/punchmark: a
shipped feature spec is a versioned identity change (PMK-FEA-003), and this is an
exploratory probe whose scoring math otherwise mirrors the shipped detector exactly
(Jeffreys-smoothed per-(task, route) multinomial, per-gram-normalised row
log-likelihood, PMK-FEA-002 draw pooling, CANON@1 view, the same global crossfit fold
map and the same subsample seed stream as the committed c2).

Both outcomes are reportable. Chance again: the paper's bound gains instrument
robustness beyond its own family. Separation: the "at chance" claim narrows to the
shipped detector family and the paper says so. The long task runs too, as a sanity
check that the probe families are not simply broken.

Reconciliation: the shipped 3-5-gram family is run through this script's own local
implementation first and must reproduce the committed c2 three-way rates exactly.

Reads the purchased archives only; issues no requests.

Usage:  .venv/bin/python validation/angle_c/short_probe.py [--write]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from zlib import crc32

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import random  # noqa: E402

from evaluate import (  # noqa: E402
    SIDE_CANDIDATES,
    load_purchased,
    subsample_identification,
)

from punchmark.calibrate import (  # noqa: E402
    cluster_subset,
    crossfit_scored,
    identify,
)
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.views import apply_view  # noqa: E402

OUT = HERE / "derived" / "short_probe.json"
SEED = 20260806
TASKS = ("comprehend", "refactor_dev")
VIEW = "CANON@1"
N_BUCKETS = 1 << 18
MASK = N_BUCKETS - 1
LAM = 0.5   # Jeffreys, as shipped (detector.py _LAMBDA)
L70 = ("deepinfra/Llama-3.3-70B-Instruct-Turbo", "together/Llama-3.3-70B-Instruct-Turbo")

FAMILIES = {
    "shipped_3_5_gram": ("char", (3, 4, 5)),   # reconciliation family
    "hi_6_8_gram": ("char", (6, 7, 8)),
    "word_1_2_gram": ("word", (1, 2)),
}


def gram_counts(text: str, kind: str, orders: tuple[int, ...]) -> Counter:
    counts: Counter[int] = Counter()
    if kind == "char":
        for n in orders:
            if len(text) < n:
                continue
            for i in range(len(text) - n + 1):
                counts[crc32(text[i:i + n].encode("utf-8")) & MASK] += 1
    else:
        toks = text.split()
        for n in orders:
            if len(toks) < n:
                continue
            for i in range(len(toks) - n + 1):
                gram = " ".join(toks[i:i + n])
                counts[crc32(gram.encode("utf-8")) & MASK] += 1
    return counts


def row_counts(raw_outputs, kind: str, orders) -> dict[int, int]:
    """PMK-FEA-002 pooling: dedup draws, scale by multiplicity."""
    mult = Counter(raw_outputs)
    pooled: Counter[int] = Counter()
    for text, m in mult.items():
        viewed = apply_view(VIEW, text)
        if not viewed:
            continue
        c = gram_counts(viewed, kind, orders)
        for b, v in c.items():
            pooled[b] += v * m
    return dict(pooled)


class ProbeFitted:
    def __init__(self, tables: dict, kind: str, orders):
        self.tables = tables
        self.kind = kind
        self.orders = orders

    def score_rows(self, rows, task):
        out = []
        for r in rows:
            counts = row_counts(r.raw_outputs, self.kind, self.orders)
            total = sum(counts.values())
            scores = {}
            for route, (log_theta, log_unseen) in self.tables[task].items():
                if total == 0:
                    scores[route] = 0.0
                    continue
                s = sum(c * log_theta.get(b, log_unseen) for b, c in counts.items())
                scores[route] = round(s / total, 6)
            out.append(scores)
        return out


class ProbeDetector:
    """The shipped multinomial with a swappable gram family: theta = (c + 0.5) /
    (C + 0.5 * D), per-gram-normalised row log-likelihood, logs rounded to 6."""

    def __init__(self, kind: str, orders):
        self.kind = kind
        self.orders = orders

    def fit(self, train, candidates, seed):
        tables: dict[str, dict] = {}
        for rs in train:
            pooled: Counter[int] = Counter()
            for r in rs.valid_rows:
                pooled.update(row_counts(r.raw_outputs, self.kind, self.orders))
            total = sum(pooled.values())
            denom = total + LAM * N_BUCKETS
            log_theta = {
                b: round(math.log((c + LAM) / denom), 6) for b, c in pooled.items()
            }
            log_unseen = round(math.log(LAM / denom), 6)
            tables.setdefault(rs.task, {})[rs.route] = (log_theta, log_unseen)
        return ProbeFitted(tables, self.kind, self.orders)


def run_family(purchased, kind: str, orders) -> tuple[dict, dict]:
    oof = crossfit_scored(ProbeDetector(kind, orders), purchased, SIDE_CANDIDATES, SEED)
    rates = {}
    conf = {}
    for ss in oof:
        m = min(25, sum(len(v) for v in ss.clusters.values()))
        rates[f"{ss.route}|{ss.task}"] = round(
            subsample_identification(ss, m, 1000, "main"), 4
        )
        # Seed-matched confusion, mirroring evaluate.confusion()'s stream.
        counts = dict.fromkeys(SIDE_CANDIDATES.routes, 0)
        for i in range(1000):
            rng = random.Random(derive_seed("c2-ident", "main", ss.source_name,
                                            m, i, SEED))
            counts[identify(cluster_subset(ss.clusters, m, rng),
                            SIDE_CANDIDATES.routes)] += 1
        conf[f"{ss.route}|{ss.task}"] = {r: c / 1000 for r, c in counts.items()}
    return rates, conf


def binary_pair_mean(conf: dict, task: str) -> float:
    vals = []
    for r in L70:
        row = conf[f"{r}|{task}"]
        other = next(x for x in L70 if x != r)
        vals.append(row[r] / (row[r] + row[other]))
    return round(sum(vals) / len(vals), 4)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    committed = json.loads(
        (HERE / "derived" / "angle_c_evaluation.json").read_text(encoding="utf-8")
    )["c2_identification_side_model"]["per_archive"]

    purchased = load_purchased()
    families_out = {}
    for name, (kind, orders) in FAMILIES.items():
        rates, conf = run_family(purchased, kind, orders)
        if name == "shipped_3_5_gram":
            for key, want in committed.items():
                if rates[key] != want["subsample_identification_rate"]:
                    raise SystemExit(
                        f"reconciliation failed at {key}: local implementation "
                        f"gives {rates[key]}, committed "
                        f"{want['subsample_identification_rate']}"
                    )
            print("reconciled: local 3-5-gram implementation matches committed c2")
        binaries = {t: binary_pair_mean(conf, t) for t in TASKS}
        families_out[name] = {
            "kind": kind,
            "orders": list(orders),
            "three_way_identification": rates,
            "binary_pair_mean_by_task": binaries,
        }
        print(f"{name:20s} binary pair mean: {binaries}")

    body = {
        "punchmark_schema": "angle_c_short_probe/v1",
        "seed": SEED,
        "question": (
            "is the short task's at-chance result a property of the text channel "
            "or of the shipped 3-5-gram family? Two stronger families through the "
            "identical pipeline, same fold map, same subsample seed stream"
        ),
        "reconciliation": {
            "local_3_5_gram_matches_committed_c2": True,
        },
        "chance": {"three_way": 0.3333, "binary": 0.5},
        "families": families_out,
        "scope": (
            "an exploratory probe implemented in validation only; the shipped "
            "feature spec is unchanged (a spec addition is a versioned identity "
            "change, PMK-FEA-003). No number here is a capability claim about any "
            "model; identification is separability within a closed candidate set"
        ),
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(body))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/short_probe.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
