"""Property tests: the reader survives any interleaving of the shapes it accepts,
and its counts always reconcile (PMK-ARC-002/003)."""

from __future__ import annotations

import gzip
import json
import random
from pathlib import Path

from punchmark.archive import read_archive


def _random_rows(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    n = rng.randint(1, 40)
    for i in range(n):
        kind = rng.random()
        if kind < 0.15:
            rows.append(
                {
                    "sample": f"s{i}",
                    "profile": rng.choice(["minimal", "standard", "max"]),
                    "language": rng.choice(["python", "go"]),
                }
            )
        else:
            row = {
                "sample": f"s{i}",
                "variant": rng.choice(["base", "v0", "v1"]),
                "profile": rng.choice(["minimal", "standard", "max"]),
                "language": rng.choice(["python", "go"]),
                "intrinsic": {"n_ops": rng.randint(1, 5)},
                "raw_outputs": ["x" * rng.randint(1, 30)] * rng.randint(1, 8),
            }
            if rng.random() < 0.5:
                row["tier"] = rng.choice(["A", "B", "C"])
            rows.append(row)
    return rows


def test_reader_reconciles_on_random_interleavings(tmp_path: Path) -> None:
    for trial in range(25):
        rng = random.Random(1000 + trial)
        rows = _random_rows(rng)
        path = tmp_path / f"t{trial}__some-route.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        rs = read_archive(path)
        assert len(rs.rows) == len(rows)
        n_stubs = sum(1 for r in rows if "raw_outputs" not in r)
        assert rs.n_stub_rows == n_stubs
        assert len(rs.valid_rows) == len(rows) - n_stubs
        assert all(r.raw_outputs for r in rs.valid_rows)
        for row in rs.valid_rows:
            assert row.cluster == row.sample
