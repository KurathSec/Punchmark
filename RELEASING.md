# Releasing

1. Ensure `main` is green: tests, ruff, mypy --strict, the three mechanical gates,
   `tools/update_calibration.py --check`, and `tools/render_rulings.py --check`.
2. Move `src/punchmark/_version.py` to the release version; move the `Unreleased`
   section of CHANGELOG.md under the new version heading. If any spec ruling was
   superseded since the last release, the rulings-spec MAJOR must already have moved
   with it. Check `punchmark spec version`.
3. Commit, tag `v<version>`, push the tag. `.github/workflows/release.yml` enforces:
   - tag == `_version.py` == newest CHANGELOG heading
   - the sdist ships none of `.github/`, `CLAUDE.md`, `site/`, `scratch/`, `paper/`,
     `calibration/`, `validation/`
   - the built wheel passes the offline smoke roundtrip
     (`synth -> fit -> score -> certify -> gate`)
4. PyPI publishing is automatic and needs no local step. A second job in the same
   workflow uploads the built artifacts via PyPI trusted publishing, so there is no API
   token in this repository. It runs only after `build` passes, because a version number
   on PyPI can never be reused. It routes through the `pypi` GitHub environment, so any
   protection rule set there (required reviewers, wait timer) gates the upload.
5. Zenodo archives from a **published GitHub Release**, not from the tag. Pushing the tag
   alone does not fire the webhook. Create the release from the tag once the workflow is
   green. `CITATION.cff` deliberately omits `version` and `date-released`; Zenodo takes
   both from the release.

## Name contingency

The distribution name is `punchmark` (PyPI simple index returned 404 on 2026-08-03). If
the name is squatted before the first upload, publish as `punchmark-eval` with the
import package and CLI unchanged (`punchmark`), mirroring the limen / limen-eval
precedent. The rename touches exactly: `[project] name` in pyproject.toml, the
`pip install "punchmark==..."` line in action.yml, the install line in
docs/quickstart.md and README.md, and this file. Record the decision here.

## After the release

Bump `_version.py` to the next `.dev0` and open a fresh `Unreleased` section in the
changelog. If the release moved the calibration (detector version or spec MAJOR),
refresh `calibration/*/goldens/` in the same commit that moved it. The drift gate
enforces the pairing.
