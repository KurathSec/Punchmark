# Releasing

1. Ensure `main` is green: tests, ruff, mypy --strict, the three mechanical gates, and
   `tools/update_calibration.py --check`.
2. Move `src/punchmark/_version.py` to the release version; move the `Unreleased`
   section of CHANGELOG.md under the new version heading. If any spec ruling was
   superseded since the last release, the rulings-spec MAJOR must already have moved
   with it -- check `punchmark spec version`.
3. Commit, tag `v<version>`, push the tag. `.github/workflows/release.yml` enforces:
   tag == `_version.py` == newest CHANGELOG heading; the sdist ships none of `.github/`,
   `CLAUDE.md`, `site/`, `scratch/`, `paper/`, `calibration/`, `validation/`; the built
   wheel passes the offline smoke roundtrip (`synth -> fit -> score -> certify -> gate`).
4. Publish to PyPI from the workflow's artifacts.

## Name contingency

The distribution name is `punchmark` (PyPI simple index returned 404 on 2026-08-03). If
the name is squatted before the first upload, publish as `punchmark-eval` with the
import package and CLI unchanged (`punchmark`), mirroring the limen / limen-eval
precedent. Record the decision here.

## After the release

Bump `_version.py` to the next `.dev0` and open a fresh `Unreleased` section in the
changelog. If the release moved the calibration (detector version or spec MAJOR),
refresh `calibration/*/goldens/` in the same commit that moved it -- the drift gate
enforces the pairing.
