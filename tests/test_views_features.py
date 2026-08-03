"""Views and feature extraction: pooling arithmetic and text-only discipline
(PMK-FEA-001/002/003)."""

from __future__ import annotations

import pytest

from punchmark.errors import FeatureError
from punchmark.features import get_spec, n_distinct_draws, row_counts
from punchmark.views import apply_view


def test_raw_view_is_identity() -> None:
    assert apply_view("RAW@1", "  a\tb\n") == "  a\tb\n"


def test_canon_strips_one_outer_fence_and_collapses_whitespace() -> None:
    text = "```python\ndef  f():\n\n\n    return   1\n```"
    out = apply_view("CANON@1", text)
    assert "```" not in out
    assert "def f():" in out
    assert "\n\n" not in out
    # case preserved
    assert apply_view("CANON@1", "CamelCase") == "CamelCase"


def test_canon_leaves_unfenced_text_alone_apart_from_whitespace() -> None:
    assert apply_view("CANON@1", "plain   text") == "plain text"


def test_abl_recipe_lowercases_strips_fences_truncates() -> None:
    text = "```Go\n" + "WORD " * 100 + "\n```"
    out = apply_view("ABL@1", text)
    assert out == out.lower()
    assert "```" not in out
    assert len(out) <= 200


def test_unknown_view_and_spec_refused() -> None:
    with pytest.raises(FeatureError, match="unknown text view"):
        apply_view("NOPE@9", "x")
    with pytest.raises(FeatureError, match="unknown feature spec"):
        get_spec("nope/v9")


def test_row_counts_pooling_equals_counting_every_draw() -> None:
    draws = ["abcabc", "abcabc", "xyz"]
    pooled = row_counts(draws, "RAW@1", "chargram1/v1")
    # counting each draw independently and summing must give the same buckets
    single = {}
    for d in draws:
        for bucket, c in row_counts([d], "RAW@1", "chargram1/v1").items():
            single[bucket] = single.get(bucket, 0) + c
    assert pooled == single


def test_row_counts_refuses_empty_draws() -> None:
    with pytest.raises(FeatureError, match="stubs are never featurized"):
        row_counts([], "RAW@1", "chargram1/v1")


def test_n_distinct_draws() -> None:
    assert n_distinct_draws(["a", "a", "b"]) == 2


def test_featurizer_signature_is_text_only() -> None:
    """PMK-FEA-001: the featurizer accepts strings; there is no row-shaped input
    through which identity metadata could leak."""
    import inspect

    sig = inspect.signature(row_counts)
    assert list(sig.parameters) == ["raw_outputs", "view", "spec_id"]
