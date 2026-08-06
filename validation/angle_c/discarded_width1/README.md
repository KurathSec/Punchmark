# Discarded: 54 items collected at fan-out width 1

These rows were bought and then dropped. They are kept rather than deleted because a
study that reports a spend should be able to account for all of it, including the part
that bought nothing.

## What they are

The first 54 items of `comprehend` on `deepinfra-llama70b`, collected 2026-08-06,
432 calls, 420,146 tokens, about $0.25 at the pinned $0.60/Mtok.

## Why they were discarded

The first version of `collect.py` issued every request sequentially: one item at a time,
one draw at a time, network fan-out width 1. The June collection these archives are
compared against did not. Its `run_meta` sidecars record `net_concurrency` explicitly,
and it is 48 for every `comprehend` archive and 128 for every `refactor` archive, on all
four routes, in both splits.

Width is not only a speed setting. Hosted inference servers batch concurrent requests
continuously, so the width determines which requests share a batch, which determines the
reduction order of the floating-point accumulations inside a batched kernel. At
temperature 0 a token that is close to a tie can flip on that alone. Serving-side
variation of exactly this kind is why the upstream harness documents that "model outputs
are not byte-deterministic even at temperature=0" and records k samples rather than one.

That makes the width a property of the collection, not of the producer, and this study
reads text to make claims about producers. Two things follow:

- A fresh archive collected at width 1 compared against a June archive collected at
  width 48 would confound the collection method with five weeks of drift, which is the
  comparison the DeepInfra side is supposed to supply.
- The two sides of the load-bearing pair must be collected at one width as each other,
  or provider is confounded with batching.

Mixing widths *inside* one archive is worse than either, because there is then no single
width to declare for it. 54 items had been written when the discrepancy was found, so the
task was restarted from empty at the June widths and these rows were moved here.

## What this does not claim

That the width-1 rows are wrong, or that they differ from the width-48 rows at all. The
effect described above is a possibility that this collection is not designed to measure,
and no comparison between these rows and the replacement archive appears anywhere in the
study. They were discarded because the collection method should be uniform and declared,
not because a difference was observed.
