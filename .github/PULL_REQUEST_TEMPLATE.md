## What and why

<!-- What was wrong, and what evidence shows it is fixed. -->

## Checklist

- [ ] `pytest` green, including the three mechanical gates (operating-point
      drift, spec coverage, layering). **No gate was worked around.**
- [ ] `ruff check src tests tools validation` and `mypy` (strict) green.
- [ ] Every load-bearing choice that changed carries a numbered spec ruling --
      added or superseded with a version bump, never edited -- cited from the
      code and pinned by a test.
- [ ] No benchmark-result claim was introduced. Nothing in this repository
      states or implies a finding about the capabilities of any model.
