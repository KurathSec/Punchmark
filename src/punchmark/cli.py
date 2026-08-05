"""``punchmark``: argparse wiring only; every verb is thin over one module.

Exit-code discipline (PMK-GTE-001): fit/score exit 0 when a measurement was
recorded (a SUBSTITUTED ruling is a successful measurement, not an error), 1 on a
typed refusal, 2 on usage errors or unevaluable input. certify is tri-state on
the verdict itself: 0 HOLDS, 1 DOES NOT HOLD, 2 UNDETERMINED or unevaluable.
"""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from ._version import __version__
from .archive import modal_k, ragged_rows, read_archive
from .calibrate import CalibrationConfig, calibrate
from .canonical import sha256_file
from .certify import certificate_from_ruling, certificate_json, exit_code_for
from .corpus import build_manifest, read_manifest, verify_shipped, verify_sources
from .detector import build_detector
from .errors import GateError, PunchmarkError
from .gate import baseline_body, evaluate, read_baseline
from .model import CandidateSet, ResponseSet, Ruling, Verdict
from .modelfile import build_doc, read_model, write_model
from .power import PowerConfig, power_analysis
from .rulings import DEFAULT_STORE, append, find, verify
from .score import RulePolicy, rule
from .sidecar import load_and_attach
from .spec import all_decisions, require, spec_version
from .synth import SynthSpec, default_routes, generate

# The corpus identity of an ad-hoc fit: a manifest built over the training archives
# themselves, so even an uncommitted calibration has a real, reproducible hash.
_ADHOC_CHECKOUT = {"repo": "ad-hoc", "commit": "unpinned"}


def _model_path(arg: str) -> Path:
    """Resolve --model: a path, or the literal 'default' for the shipped reference
    model (fitted on the reference corpus's fit-role archives; PMK-COR-002)."""
    if arg == "default":
        from importlib import resources

        return Path(str(resources.files("punchmark").joinpath("models/default.pmk.json")))
    return Path(arg)


def _read_windowed(
    path: Path, candidates: CandidateSet | None, sidecar_dir: str | None = None
) -> ResponseSet:
    rs = read_archive(path, candidates)
    return load_and_attach(rs, path, Path(sidecar_dir) if sidecar_dir else None)


def _record(store: Path, ruling_obj: Ruling) -> bool:
    """Append a ruling unless the identical ruling is already recorded: identical
    inputs reproduce identical ids (PMK-RUL-004), so a re-run is idempotent rather
    than a refusal. Returns True when the store gained a line."""
    from .rulings import verify as _verify

    if any(b["ruling_id"] == ruling_obj.ruling_id for b in _verify(store)):
        print(f"  ruling {ruling_obj.ruling_id} already recorded in {store}")
        return False
    append(store, ruling_obj)
    return True


def _parse_floats(text: str) -> tuple[float, ...]:
    return tuple(float(x) for x in text.split(",") if x)


def _parse_ints(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split(",") if x)


def _cmd_fit(args: argparse.Namespace) -> int:
    try:
        far_grid = _parse_floats(args.far_grid)
        m_grid = _parse_ints(args.m_grid)
    except ValueError as exc:
        print(f"usage: --far-grid/--m-grid must be comma-separated numbers ({exc})",
              file=sys.stderr)
        return 2
    candidates = CandidateSet(routes=tuple(sorted(set(args.candidates.split(",")))))
    paths = [Path(p) for p in args.archives]
    train = [_read_windowed(p, candidates, args.sidecars) for p in paths]
    detector = build_detector(args.detector, view=args.view)
    cal_config = CalibrationConfig(
        far_grid=far_grid,
        m_grid=m_grid,
        n_null=args.n_null,
        seed=args.seed,
        min_clusters=args.min_clusters,
    )
    pow_config = PowerConfig(
        n_splice=args.n_splice, power_target=args.power_target, seed=args.seed
    )
    calibration = calibrate(detector, train, candidates, cal_config)
    power = power_analysis(
        calibration.oof_scored, candidates, calibration.operating_points,
        cal_config, pow_config,
    )
    fitted = detector.fit(train, candidates, args.seed)
    if args.corpus:
        manifest = read_manifest(Path(args.corpus))
        corpus_sha = manifest.corpus_sha256
    else:
        manifest = build_manifest(
            mode="manifest",
            checkout=dict(_ADHOC_CHECKOUT),
            sources=[
                {"path": p.name, "sha256": sha256_file(p)} for p in sorted(paths)
            ],
            files=[],
            note="ad-hoc manifest built by punchmark fit over its training archives",
        )
        corpus_sha = manifest.corpus_sha256
    doc = build_doc(
        fitted=fitted,
        spec_version=spec_version(),
        calibration_sha256=corpus_sha,
        calibration_meta={
            "far_grid": list(cal_config.far_grid),
            "m_grid": list(cal_config.m_grid),
            "n_null": cal_config.n_null,
            "n_splice": pow_config.n_splice,
            "power_target": pow_config.power_target,
            "seed": args.seed,
        },
        operating_points=calibration.operating_points,
        curve=power.curve,
        power=power.power_points,
    )
    out = Path(args.out)
    write_model(out, doc)
    print(f"fitted {doc.model_id} -> {out}")
    print(f"candidates: {', '.join(candidates.routes)}  (set {candidates.candidate_set_id})")
    print(f"calibration corpus: {corpus_sha}")
    print("operating points (task, far, m -> threshold):")
    for p in sorted(doc.operating_points, key=lambda p: (p.task, p.far, p.m)):
        print(f"  {p.task}  far={p.far}  m={p.m}  t={p.threshold:.6f}  (n_null={p.n_null})")
    print("miss-rate-versus-false-alarm curve (worst pair per task, largest m):")
    for task in doc.tasks:
        largest = max(c.m for c in doc.curve if c.task == task)
        for far in sorted({c.far for c in doc.curve if c.task == task}):
            worst = max(
                (c for c in doc.curve if c.task == task and c.far == far and c.m == largest),
                key=lambda c: c.miss,
            )
            print(
                f"  {task}  m={largest}  far={far}  miss={worst.miss:.3f}  "
                f"(worst pair {worst.declared} vs {worst.substitute})"
            )
    far_shown = 0.01 if any(pw.far == 0.01 for pw in doc.power) else min(
        pw.far for pw in doc.power
    )
    print(
        f"minimum resolvable substituted fraction rho* "
        f"(per ordered pair, largest m, far={far_shown}):"
    )
    for task in doc.tasks:
        largest = max(pw.m for pw in doc.power if pw.task == task)
        for pw in sorted(
            (
                pw for pw in doc.power
                if pw.task == task and pw.m == largest and pw.far == far_shown
            ),
            key=lambda pw: (pw.declared, pw.substitute),
        ):
            shown = "unresolvable at rho<=1.0" if pw.rho_min is None else f"{pw.rho_min}"
            print(f"  {task}  {pw.declared} <- {pw.substitute}  rho*={shown}")
    print(
        "note: seeded substitutions are a best case; their fidelity to real vendor "
        "changes cannot be validated and stands as a bound (PMK-POW-004)."
    )
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    doc = read_model(_model_path(args.model))
    rs = _read_windowed(Path(args.archive), doc.candidates, args.sidecars)
    policy = RulePolicy(
        far=args.far,
        rho_target=args.rho_target,
        m_floor=args.m_floor,
        c_floor=args.c_floor,
        stub_cap=args.stub_cap,
    )
    ruling = rule(doc, rs, policy, spec_version(), scored_as=args.task_as)
    store = Path(args.rulings)
    appended = _record(store, ruling)
    print(f"{ruling.verdict.value}  route={ruling.route}  task={ruling.task}")
    print(
        f"  T={ruling.statistic if ruling.statistic is not None else 'n/a'}  "
        f"threshold={ruling.threshold if ruling.threshold is not None else 'n/a'}  "
        f"far={ruling.far}"
    )
    if ruling.reasons:
        for reason in ruling.reasons:
            print(f"  reason: {reason}")
    print(f"  items={ruling.n_items} clusters={ruling.n_clusters} stubs={ruling.n_stub_rows}")
    if appended:
        print(f"  ruling {ruling.ruling_id} appended to {store}")
    return 0


def _cmd_certify(args: argparse.Namespace) -> int:
    # Tri-state discipline (PMK-GTE-001, PMK-CRT-001): exit 1 means exactly one
    # thing -- a measured DOES NOT HOLD. Refusals and unevaluable inputs land on
    # exit 2 with UNDETERMINED, never on the measured-failure code.
    try:
        return _certify_inner(args)
    except PunchmarkError as exc:
        print(f"unevaluable: {exc}", file=sys.stderr)
        return 2


def _certify_inner(args: argparse.Namespace) -> int:
    store = Path(args.rulings)
    if args.ruling:
        body = find(store, args.ruling)
    else:
        if not args.archive or not args.model:
            print(
                "certify needs either --ruling ID or an ARCHIVE with --model",
                file=sys.stderr,
            )
            return 2
        doc = read_model(_model_path(args.model))
        rs = _read_windowed(Path(args.archive), doc.candidates, args.sidecars)
        policy = RulePolicy(far=args.far, rho_target=args.rho_target)
        ruling = rule(doc, rs, policy, spec_version(), scored_as=args.task_as)
        _record(store, ruling)
        body = find(store, ruling.ruling_id)
    cert = certificate_from_ruling(body)
    print(cert.line)
    if args.out:
        from .canonical import write_text_deterministic

        write_text_deterministic(Path(args.out), certificate_json(cert))
        print(f"certificate written to {args.out}", file=sys.stderr)
    if args.json:
        print(certificate_json(cert), end="")
    return exit_code_for(Verdict(body["verdict"]))


def _cmd_gate(args: argparse.Namespace) -> int:
    doc = read_model(_model_path(args.model))
    if args.write_baseline:
        from .canonical import canonical_json, write_text_deterministic

        write_text_deterministic(Path(args.baseline), canonical_json(baseline_body(doc)))
        print(f"baseline written to {args.baseline}")
        return 0
    baseline = read_baseline(Path(args.baseline))
    result = evaluate(doc, baseline, spec_version())
    for line in result.lines:
        print(line)
    if args.require_chain_valid:
        store = Path(args.rulings)
        if not store.exists():
            raise GateError(
                f"--require-chain-valid: no rulings store at {store}; a chain that "
                "checked nothing has not validated anything (PMK-GTE-002)"
            )
        bodies = verify(store)
        if not bodies:
            raise GateError(
                f"--require-chain-valid: {store} contains no rulings; an empty "
                "chain validates nothing (PMK-GTE-002)"
            )
        print(f"gate: ruling chain valid ({len(bodies)} rulings)")
    return result.exit_code


def _cmd_corpus(args: argparse.Namespace) -> int:
    corpus_dir = Path(args.corpus)
    manifest = read_manifest(corpus_dir)
    if args.corpus_cmd == "verify":
        for line in verify_shipped(corpus_dir, manifest):
            print(line)
        if args.source:
            for line in verify_sources(manifest, Path(args.source)):
                print(line)
        return 0
    # rebuild
    if not args.source:
        print("corpus rebuild requires --source <checkout>", file=sys.stderr)
        return 2
    for line in verify_sources(manifest, Path(args.source)):
        print(line)
    return 0


def _cmd_synth(args: argparse.Namespace) -> int:
    spec = SynthSpec(
        routes=default_routes(args.routes),
        tasks=tuple(args.tasks.split(",")),
        n_clusters=args.clusters,
        k=args.k,
        separation=args.separation,
        seed=args.seed,
    )
    paths = generate(Path(args.out), spec)
    for p in paths:
        print(p)
    return 0


def _cmd_spec(args: argparse.Namespace) -> int:
    if args.spec_cmd == "version":
        print(spec_version())
    elif args.spec_cmd == "list":
        for d in all_decisions():
            marker = "" if d.status == "active" else f"  [{d.status}]"
            print(f"{d.id}  {d.title}{marker}")
    else:
        d = require(args.id)
        print(f"{d.id}: {d.title}\n\n{d.text}")
    return 0


def _cmd_census(args: argparse.Namespace) -> int:
    path = Path(args.archive)
    rs = read_archive(path)
    print(f"{rs.source_name}: task={rs.task} label={rs.route}")
    print(f"  rows={len(rs.rows)} valid={len(rs.valid_rows)} stubs={rs.n_stub_rows}")
    print(f"  clusters={len(rs.clusters)} modal_k={modal_k(rs)} ragged={ragged_rows(rs)}")
    print(f"  sha256={rs.archive_sha256}")
    return 0


def _cmd_env(args: argparse.Namespace) -> int:
    del args
    print(f"punchmark {__version__}")
    print(f"spec {spec_version()}")
    print(f"python {platform.python_version()} ({platform.platform()})")
    print("runtime dependencies: none")
    return 0


def _cmd_cite(args: argparse.Namespace) -> int:
    del args
    print(
        "Ji, Yuxiang. punchmark: a retrospective producer identifier for hosted "
        f"LLM routes (version {__version__}). https://github.com/KurathSec/Punchmark"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="punchmark",
        description=(
            "A retrospective producer identifier: point it at the response archive a "
            "benchmark number was computed on and get a SAME-PRODUCER / SUBSTITUTED / "
            "UNDETERMINED ruling at a declared false-alarm rate, with a certificate "
            "attachable to the published score. Verdicts are about the route label as "
            "served, never about weights."
        ),
    )
    parser.add_argument("--version", action="version", version=f"punchmark {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fit", help="fit and calibrate a detector over labelled archives")
    p.add_argument("archives", nargs="+", metavar="ARCHIVE")
    p.add_argument("--candidates", required=True, help="comma-separated route names")
    p.add_argument("--out", required=True, help="output .pmk-model.json path")
    p.add_argument("--detector", default="chargram")
    p.add_argument("--view", help="text view for the chargram detector (default CANON@1)")
    p.add_argument("--far-grid", default="0.001,0.005,0.01,0.05,0.1")
    p.add_argument("--m-grid", default="25,50,100,150")
    p.add_argument("--n-null", type=int, default=2000)
    p.add_argument("--n-splice", type=int, default=400)
    p.add_argument("--power-target", type=float, default=0.8)
    p.add_argument("--min-clusters", type=int, default=8)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--corpus", help="calibration corpus dir (its manifest becomes the identity)")
    p.add_argument("--sidecars", help="directory holding <archive>.window.json sidecars")
    p.set_defaults(fn=_cmd_fit)

    p = sub.add_parser("score", help="rule one archive against a fitted model")
    p.add_argument("archive", metavar="ARCHIVE")
    p.add_argument("--model", required=True)
    p.add_argument("--far", type=float, default=0.01)
    p.add_argument("--rho-target", type=float, default=1.0)
    p.add_argument("--m-floor", type=int, default=25)
    p.add_argument("--c-floor", type=int, default=8)
    p.add_argument("--stub-cap", type=float, default=0.05)
    p.add_argument("--rulings", default=str(DEFAULT_STORE))
    p.add_argument("--sidecars", help="directory holding <archive>.window.json sidecars")
    p.add_argument(
        "--task-as",
        help="score this archive under a calibrated model task of the same family "
        "(recorded in the ruling as scored_as; never inferred; PMK-RUL-005)",
    )
    p.set_defaults(fn=_cmd_score)

    p = sub.add_parser("certify", help="emit the certificate for a ruling")
    p.add_argument("archive", nargs="?", metavar="ARCHIVE")
    p.add_argument("--ruling", help="certify an existing ruling id")
    p.add_argument("--model")
    p.add_argument("--far", type=float, default=0.01)
    p.add_argument("--rho-target", type=float, default=1.0)
    p.add_argument("--rulings", default=str(DEFAULT_STORE))
    p.add_argument("--out", help="write the certificate JSON here")
    p.add_argument("--json", action="store_true", help="print the certificate JSON to stdout")
    p.add_argument("--sidecars", help="directory holding <archive>.window.json sidecars")
    p.add_argument(
        "--task-as",
        help="score this archive under a calibrated model task of the same family "
        "(recorded in the ruling as scored_as; never inferred; PMK-RUL-005)",
    )
    p.set_defaults(fn=_cmd_certify)

    p = sub.add_parser("gate", help="CI gate: fail when the operating point moved silently")
    p.add_argument("model", metavar="MODELFILE")
    p.add_argument("--baseline", required=True)
    p.add_argument("--write-baseline", action="store_true")
    p.add_argument("--require-chain-valid", action="store_true")
    p.add_argument("--rulings", default=str(DEFAULT_STORE))
    p.set_defaults(fn=_cmd_gate)

    p = sub.add_parser("corpus", help="verify or rebuild the calibration corpus")
    p.add_argument("corpus_cmd", choices=["verify", "rebuild"])
    p.add_argument("--corpus", required=True, help="corpus directory holding MANIFEST.json")
    p.add_argument("--source", help="local source checkout to verify pinned bytes against")
    p.set_defaults(fn=_cmd_corpus)

    p = sub.add_parser("synth", help="generate planted-truth synthetic archives")
    p.add_argument("--out", required=True)
    p.add_argument("--routes", type=int, default=3)
    p.add_argument("--clusters", type=int, default=12)
    p.add_argument("--k", type=int, default=4)
    p.add_argument("--separation", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--tasks", default="synthtask")
    p.set_defaults(fn=_cmd_synth)

    p = sub.add_parser("census", help="describe one archive (rows, stubs, clusters, k)")
    p.add_argument("archive", metavar="ARCHIVE")
    p.set_defaults(fn=_cmd_census)

    p = sub.add_parser("spec", help="spec rulings")
    spec_sub = p.add_subparsers(dest="spec_cmd", required=True)
    spec_sub.add_parser("version")
    spec_sub.add_parser("list")
    show = spec_sub.add_parser("show")
    show.add_argument("id")
    p.set_defaults(fn=_cmd_spec)

    p = sub.add_parser("env", help="print environment facts")
    p.set_defaults(fn=_cmd_env)

    p = sub.add_parser("cite", help="print the citation")
    p.set_defaults(fn=_cmd_cite)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result: int = args.fn(args)
        return result
    except GateError as exc:
        print(f"unevaluable: {exc}", file=sys.stderr)
        return 2
    except PunchmarkError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
