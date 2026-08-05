"""End-to-end CLI: the synth -> fit -> score -> certify -> gate roundtrip and the
exit-code discipline (PMK-GTE-001)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from punchmark.cli import main


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("cliwork")
    assert (
        main(
            [
                "synth", "--out", str(root / "arch"), "--routes", "3",
                "--clusters", "10", "--k", "2", "--separation", "0.6", "--seed", "5",
            ]
        )
        == 0
    )
    archives = sorted((root / "arch").glob("synthtask__*.jsonl.gz"))
    assert (
        main(
            [
                "fit", *[str(p) for p in archives],
                "--candidates", "synth/route-a,synth/route-b,synth/route-c",
                "--out", str(root / "model.pmk-model.json"),
                "--m-grid", "25,50", "--far-grid", "0.05,0.1",
                "--n-null", "150", "--n-splice", "40",
                "--min-clusters", "4", "--seed", "5",
            ]
        )
        == 0
    )
    return root


def test_score_true_and_substituted(workdir: Path, capsys) -> None:
    model = str(workdir / "model.pmk-model.json")
    store = str(workdir / "rulings.jsonl")
    archive = workdir / "arch" / "synthtask__synth-route-a.jsonl.gz"
    assert main(["score", str(archive), "--model", model, "--rulings", store,
                 "--far", "0.05"]) == 0
    out = capsys.readouterr().out
    assert "SAME-PRODUCER" in out

    # planted substitution: route-b bytes under a route-a label
    subst = workdir / "subst"
    subst.mkdir(exist_ok=True)
    dst = subst / "synthtask__synth-route-a.jsonl.gz"
    shutil.copyfile(workdir / "arch" / "synthtask__synth-route-b.jsonl.gz", dst)
    digest = "sha256:" + hashlib.sha256(dst.read_bytes()).hexdigest()
    sidecar = {
        "punchmark_schema": "window/v1",
        "archive": dst.name,
        "archive_sha256": digest,
        "route": "synth/route-a",
        "task": "synthtask",
        "window": {
            "start_utc": "2026-01-01T00:00:00+00:00",
            "end_utc": "2026-01-01T01:00:00+00:00",
        },
        "collector": {},
        "declared_by": "test",
    }
    Path(str(dst) + ".window.json").write_text(json.dumps(sidecar) + "\n")
    # a recorded SUBSTITUTED measurement is still exit 0
    assert main(["score", str(dst), "--model", model, "--rulings", store,
                 "--far", "0.05"]) == 0
    assert "SUBSTITUTED" in capsys.readouterr().out


def test_certify_exit_codes_follow_the_verdict(workdir: Path, capsys) -> None:
    store = str(workdir / "rulings.jsonl")
    lines = [
        json.loads(line)
        for line in (workdir / "rulings.jsonl").read_text().splitlines()
    ]
    holds = next(b for b in lines if b["verdict"] == "SAME-PRODUCER")
    broken = next(b for b in lines if b["verdict"] == "SUBSTITUTED")
    assert main(["certify", "--ruling", holds["ruling_id"], "--rulings", store]) == 0
    out = capsys.readouterr().out
    assert "HOLDS" in out and "not a statement about model weights" in out
    assert main(["certify", "--ruling", broken["ruling_id"], "--rulings", store]) == 1
    assert "DOES NOT HOLD" in capsys.readouterr().out


def test_certify_without_inputs_is_usage_error(workdir: Path, capsys) -> None:
    assert main(["certify", "--rulings", str(workdir / "rulings.jsonl")]) == 2


def test_gate_roundtrip_and_tamper(workdir: Path, capsys) -> None:
    model = str(workdir / "model.pmk-model.json")
    baseline = str(workdir / "baseline.json")
    store = str(workdir / "rulings.jsonl")
    assert main(["gate", model, "--baseline", baseline, "--write-baseline"]) == 0
    assert (
        main(["gate", model, "--baseline", baseline, "--require-chain-valid",
              "--rulings", store])
        == 0
    )
    capsys.readouterr()
    # a moved threshold in the baseline (simulating a silent recalibration)
    body = json.loads(Path(baseline).read_text())
    body["operating_points"][0]["threshold"] += 1.0
    Path(baseline).write_text(json.dumps(body, sort_keys=True, indent=2) + "\n")
    assert main(["gate", model, "--baseline", baseline]) == 1
    assert "moved" in capsys.readouterr().out


def test_refusal_exit_codes(workdir: Path, tmp_path: Path, capsys) -> None:
    model = str(workdir / "model.pmk-model.json")
    # missing sidecar -> refusal (1), and the message prints the shape to write
    bare = tmp_path / "synthtask__synth-route-a.jsonl.gz"
    shutil.copyfile(workdir / "arch" / "synthtask__synth-route-a.jsonl.gz", bare)
    assert main(["score", str(bare), "--model", model, "--far", "0.05",
                 "--rulings", str(tmp_path / "r.jsonl")]) == 1
    err = capsys.readouterr().err
    assert "window/v1" in err
    # unreadable baseline -> unevaluable (2)
    assert main(["gate", model, "--baseline", str(tmp_path / "missing.json")]) == 2


def test_census_and_spec_and_env(workdir: Path, capsys) -> None:
    archive = workdir / "arch" / "synthtask__synth-route-b.jsonl.gz"
    assert main(["census", str(archive)]) == 0
    out = capsys.readouterr().out
    assert "stubs=0" in out and "clusters=10" in out
    assert main(["spec", "version"]) == 0
    assert main(["spec", "show", "PMK-CRT-002"]) == 0
    assert "No weights claim" in capsys.readouterr().out
    assert main(["env"]) == 0
    assert "runtime dependencies: none" in capsys.readouterr().out


def test_certify_unknown_ruling_is_unevaluable_not_measured_fail(
    workdir: Path, capsys
) -> None:
    """A missing ruling is unevaluable (exit 2); exit 1 means exactly one thing --
    a measured DOES NOT HOLD (PMK-GTE-001)."""
    store = str(workdir / "rulings.jsonl")
    assert main(["certify", "--ruling", "pmk-r-doesnotexist000", "--rulings", store]) == 2
    assert "unevaluable" in capsys.readouterr().err


def test_gate_chain_valid_refuses_missing_and_empty_stores(
    workdir: Path, tmp_path: Path, capsys
) -> None:
    """PMK-GTE-002: a chain that checked nothing has not validated anything."""
    model = str(workdir / "model.pmk-model.json")
    baseline = str(workdir / "chainbase.json")
    assert main(["gate", model, "--baseline", baseline, "--write-baseline"]) == 0
    capsys.readouterr()
    missing = str(tmp_path / "absent.jsonl")
    assert main(["gate", model, "--baseline", baseline,
                 "--require-chain-valid", "--rulings", missing]) == 2
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert main(["gate", model, "--baseline", baseline,
                 "--require-chain-valid", "--rulings", str(empty)]) == 2


def test_gate_malformed_baseline_is_unevaluable(workdir: Path, tmp_path: Path) -> None:
    """A baseline missing required fields exits 2, never the measured-fail code."""
    model = str(workdir / "model.pmk-model.json")
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"punchmark_schema": "gate-baseline/v1", "operating_points": [{"task": "t"}]}\n'
    )
    assert main(["gate", model, "--baseline", str(bad)]) == 2


def test_rescore_is_idempotent(workdir: Path, tmp_path: Path, capsys) -> None:
    """Identical inputs reproduce the identical ruling id, so a re-run records
    nothing new and is not a refusal (PMK-RUL-004). Self-contained: it scores
    twice into its own store rather than depending on an earlier test."""
    model = str(workdir / "model.pmk-model.json")
    store = tmp_path / "idempotent.jsonl"
    archive = workdir / "arch" / "synthtask__synth-route-a.jsonl.gz"
    argv = ["score", str(archive), "--model", model, "--rulings", str(store), "--far", "0.05"]

    assert main(argv) == 0
    first = capsys.readouterr().out
    assert "appended to" in first
    after_first = store.read_text()

    assert main(argv) == 0
    second = capsys.readouterr().out
    assert "already recorded" in second
    assert "appended to" not in second
    assert store.read_text() == after_first  # nothing new was written


def test_gate_typed_refusals_are_unevaluable_not_measured_fail(
    workdir: Path, tmp_path: Path, capsys
) -> None:
    """PMK-GTE-001: gate is tri-state, so exit 1 means exactly one thing, a measured
    fail. An unreadable model or baseline is unevaluable and exits 2."""
    baseline = str(workdir / "chainbase.json")
    model = str(workdir / "model.pmk-model.json")
    assert main(["gate", str(tmp_path / "absent.json"), "--baseline", baseline]) == 2
    assert "unevaluable" in capsys.readouterr().err
    bad_model = tmp_path / "bad.pmk-model.json"
    bad_model.write_text('{"punchmark_schema": "model/v99"}\n')
    assert main(["gate", str(bad_model), "--baseline", baseline]) == 2
    assert main(["gate", model, "--baseline", str(tmp_path / "absent-baseline.json")]) == 2


def test_fit_refuses_out_of_range_grids(workdir: Path, capsys) -> None:
    """A far outside (0, 1) or a non-positive m is a usage error (exit 2), named as
    such, rather than an unbounded value reaching calibration."""
    archives = [str(p) for p in sorted((workdir / "arch").glob("synthtask__*.jsonl.gz"))]
    common = ["fit", *archives, "--candidates",
              "synth/route-a,synth/route-b,synth/route-c", "--out", "/tmp/unused.json"]
    assert main([*common, "--far-grid", "1.5"]) == 2
    assert "strictly between 0 and 1" in capsys.readouterr().err
    assert main([*common, "--far-grid", "nan"]) == 2
    assert main([*common, "--m-grid", "0"]) == 2
    assert "must be >= 1" in capsys.readouterr().err
