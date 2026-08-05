# Calibration

Committed calibration corpora and their goldens. Repo-only: this directory is excluded
from the sdist. The shipped wheel carries only the fitted default model.

- `spaghetti/`: the reference corpus over the upstream benchmark's 16 committed
  response archives. Ships as **manifest + local rebuild** (PMK-COR-002), so no
  completion text lives here. `MANIFEST.json` pins the upstream commit and per-file
  sha256, and `punchmark corpus rebuild --corpus calibration/spaghetti --source <checkout>` verifies a local checkout
  byte-for-byte. The manifest's content hash is the corpus identity every ruling pins
  (PMK-COR-001).
- `spaghetti/goldens/`: the committed fitted model and its operating-point baseline,
  byte-compared by the drift gate (`tools/update_calibration.py --check`,
  `tests/test_operating_point_drift.py`).

The goldens are committed and the drift gate is armed, so
`tools/update_calibration.py --check` must pass. Regeneration
(`spaghetti/build_corpus.py`) refuses to overwrite goldens without
`--confirm-recalibration`, because a moved operating point must arrive together with a
declared detector-version or spec-MAJOR bump (PMK-GTE-003).
