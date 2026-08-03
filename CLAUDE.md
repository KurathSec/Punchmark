# CLAUDE.md

Project instructions for agent sessions. This file does not repeat README.md,
ARCHITECTURE.md or CHANGELOG.md; read those. ARCHITECTURE.md is authoritative over
prose; the code is authoritative over ARCHITECTURE.md.

## Commands

```
.venv/bin/pytest -q                 # tests (fast; all synthetic)
.venv/bin/ruff check src/ tests/    # lint (line 100, TID253 layering bans)
.venv/bin/mypy                      # strict over src/punchmark -- a hard gate
.venv/bin/punchmark ...             # the CLI under development
tools/update_calibration.py --check # drift gate (once calibration is committed)
tools/render_rulings.py             # regenerate docs/spec/rulings.md
```

## Mechanical gates (never work around them)

1. **Operating-point drift**: committed calibration regenerates committed goldens
   byte-for-byte. Moving a golden requires `tools/update_calibration.py --write
   --confirm-spec-bump` after a real detector-version or spec-MAJOR change. Never edit
   a golden by hand; never "fix" this gate by regenerating without the bump.
2. **Spec coverage** (`tests/test_spec.py`): every active `PMK-` ruling cited, every
   id-shaped string resolves. A new load-bearing choice gets a new ruling; an obsolete
   ruling is superseded (status change + successor), never edited or deleted.
3. **Layering** (`tests/test_layering.py` + TID253): the import DAG in ARCHITECTURE.md
   section 2. No foreign imports (`src`/`bench`/`eval`/numpy stack) anywhere, even lazy.

Rulings -- spec rulings AND verdict rulings -- are never edited into new meanings:
supersede with a new id.

## Honesty invariants (encoded in types and tests; keep them that way)

- A verdict is about the route label as served, never weights (PMK-CRT-002); the
  no-weights sentence is golden-pinned. UNDETERMINED is first-class and never rounds to
  SAME-PRODUCER or SUBSTITUTED (PMK-RUL-001); UNAVAILABLE is never PASS; an empty gate
  selection never passes (PMK-GTE-002).
- Every number in prose (README, docs, FINDING.md) traces to a re-runnable artifact
  (a committed golden, a `validation/` derived file, or a test) and is never hand-edited.
- No file in this repository states or implies a benchmark result, a model-capability
  claim, or a comparison between models.

## Sibling repositories (READ-ONLY)

`/home/kureist/Spaghetti-Architect` (upstream benchmark corpus), `/home/kureist/nonius`,
`/home/kureist/limen` are read-only reference material. Before and after any session
that touches the Spaghetti-Architect checkout, run
`git -C /home/kureist/Spaghetti-Architect status --porcelain` and confirm the output is
unchanged. Never import their code; punchmark reads archive FILES only.

## Local-only areas

`paper/` and `scratch/` are gitignored and never committed; the sdist excludes them a
second time. `calibration/` and `validation/` are committed but excluded from the sdist.
The calibration corpus ships as manifest + local rebuild (PMK-COR-002): never add
completion text from the upstream corpus to this repository.

## Test corpus rule

`tests/` fixtures are planted-truth synthetic archives: a fixture, not a benchmark. A
case whose numbers cannot be checked on paper does not belong in it.
