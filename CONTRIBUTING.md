# Contributing

## Setup

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" -c constraints/ci.txt
pytest && ruff check src tests tools && mypy
```

Python >= 3.12. There are zero runtime dependencies, and that is an intentional
constraint: `src/punchmark/` uses the standard library only. A change that needs a
third-party package needs a design discussion first.

## The three mechanical gates

`pytest` includes three tests that exist to be inconvenient. **Never work around
them.** Each guards a failure mode this tool exists to make visible in others.

- **Operating-point drift** (`tests/test_operating_point_drift.py`): the committed
  calibration regenerates its committed goldens byte-for-byte. A calibrated
  threshold may only move together with a declared detector-version change or a
  spec MAJOR bump. A silently moved threshold is the failure that `punchmark gate`
  catches downstream (PMK-GTE-003).
- **Spec coverage** (`tests/test_spec.py`): every active ruling is cited from the
  code, tests or docs, every ruling-id-shaped string resolves to a known ruling,
  and ids are unique.
- **Layering** (`tests/test_layering.py`): the import DAG, enforced by AST.
  Readers never import the analysis stack, the detector never reads files, and
  the gate consumes serialized artifacts only. Nothing imports the upstream
  benchmark checkout or the numeric stack, whether module-level or lazily.

## Superseding a ruling

A ruling id is immutable forever, so existing rulings are not edited. Changing
what an existing id *means* silently rewrites every verdict ever issued under
it. To change a decision, mark the old stanza `status = "superseded"`, add a new
ruling with a new id, and bump the rulings-spec version in
`src/punchmark/spec/rulings/index.toml`. Bump MAJOR when the meaning of any
recorded artifact changes and MINOR otherwise. `require()` refuses superseded
ids at runtime, so stale citations fail loudly.

## Adding a spec ruling

A ruling is a single decision the tool's behaviour rests on, written down
precisely so it can be argued with.

1. Add a `[[ruling]]` stanza to the right file in `src/punchmark/spec/rulings/`.
   Ids are `PMK-<AREA>-<NNN>` and are never reused.
2. Cite it from the implementing code (docstring or `require("...")`) and from a
   test that pins the behaviour. The coverage gate scans `src`, `tests`, `tools`
   and `docs` and fails an uncited ruling.
3. Bump the rulings-spec MINOR in `index.toml` and add a changelog entry.

## Commits

Lowercase `area: imperative summary`, with a body that states what was wrong and
what evidence shows it is fixed. No benchmark-result claims anywhere in the tree:
nothing in this repository states or implies a finding about the capabilities of
any model.
