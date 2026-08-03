"""Feature extraction: the only place completion text becomes numbers.

Input is the ``raw_outputs`` strings of one row and nothing else (PMK-FEA-001):
the row schema carries no logprobs, headers or timing, and this module never
receives the row's identity fields, so a feature cannot key on metadata that
correlates with split or archive.

One row is ONE evidence unit (PMK-FEA-002): at temperature 0 most draw sets are
byte-identical, so draws are pooled -- counts are computed per distinct string and
scaled by multiplicity -- and every downstream likelihood is normalized per gram,
which makes a row contribute the same weight whether its k draws collapsed to one
string or not.

Feature specs are versioned ids. ``chargram/v1``: hashed character n-grams,
orders {3,4,5}, bucket = crc32(gram) & (2^18 - 1). ``chargram1/v1`` is the
trivial reference degenerate: order {1}, 2^10 buckets. crc32 is deterministic
across processes and platforms (unlike ``hash()``); no vocabulary is stored.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from zlib import crc32

from .errors import FeatureError
from .views import apply_view


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    spec_id: str
    orders: tuple[int, ...]
    n_buckets: int


SPECS: dict[str, FeatureSpec] = {
    "chargram/v1": FeatureSpec(spec_id="chargram/v1", orders=(3, 4, 5), n_buckets=1 << 18),
    "chargram1/v1": FeatureSpec(spec_id="chargram1/v1", orders=(1,), n_buckets=1 << 10),
}


def get_spec(spec_id: str) -> FeatureSpec:
    try:
        return SPECS[spec_id]
    except KeyError:
        raise FeatureError(
            f"unknown feature spec {spec_id!r}; shipped specs: {sorted(SPECS)}"
        ) from None


def _gram_counts(text: str, spec: FeatureSpec) -> Counter[int]:
    counts: Counter[int] = Counter()
    mask = spec.n_buckets - 1
    for n in spec.orders:
        if len(text) < n:
            continue
        grams = Counter(text[i : i + n] for i in range(len(text) - n + 1))
        for gram, c in grams.items():
            counts[crc32(gram.encode("utf-8")) & mask] += c
    return counts


def row_counts(raw_outputs: Sequence[str], view: str, spec_id: str) -> dict[int, int]:
    """Pooled bucket counts for one row's draws under a view.

    Deduplicates draws first (a ~5x cost cut on temperature-0 archives) and scales
    each distinct string's counts by its multiplicity, which is arithmetically
    identical to counting every draw.
    """
    if not raw_outputs:
        raise FeatureError("row_counts called on a row with no draws; stubs are never featurized")
    spec = get_spec(spec_id)
    multiplicity = Counter(raw_outputs)
    pooled: Counter[int] = Counter()
    for text, mult in multiplicity.items():
        viewed = apply_view(view, text)
        if not viewed:
            continue
        counts = _gram_counts(viewed, spec)
        if mult == 1:
            pooled.update(counts)
        else:
            for bucket, c in counts.items():
                pooled[bucket] += c * mult
    return dict(pooled)


def n_distinct_draws(raw_outputs: Sequence[str]) -> int:
    return len(set(raw_outputs))
