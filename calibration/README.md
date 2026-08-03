# Calibration

Committed calibration corpora and their goldens. Repo-only: this directory is excluded
from the sdist; the shipped wheel carries only the fitted default model.

- `spaghetti/` -- the reference corpus over the upstream benchmark's 16 committed
  response archives. Ships as **manifest + local rebuild** (PMK-COR-002): no completion
  text lives here; `MANIFEST.json` pins the upstream commit and per-file sha256, and
  `punchmark corpus rebuild --source <checkout>` verifies a local checkout
  byte-for-byte. The manifest's content hash is the corpus identity every ruling pins
  (PMK-COR-001).
- `spaghetti/goldens/` -- the committed fitted model and its operating-point baseline,
  byte-compared by the drift gate (`tools/update_calibration.py --check`,
  `tests/test_operating_point_drift.py`).

Content lands with the calibration commit; until then the drift gate reports
"unevaluable", which is deliberately distinct from "pass" (PMK-GTE-002).
