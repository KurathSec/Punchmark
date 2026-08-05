# Angle B finding

Angle B asks whether the archive-only channel carries the producer signal that
published work obtained from crafted probes and chat text, before any new data is
purchased. Two halves, both free and archive-side. Every number traces to a committed
artifact under `derived/`.

## Half 1: per-row producer identification (`derived/per_row_identification.json`)

The closest published figure is llm-idiosyncrasies (ICML 2025): 97.1% five-way
per-response producer classification on chat text, with a trained classifier and free
sampling. This study runs the analogous measurement on this corpus: per-row four-way
producer classification on the eight held-out archives, using the shipped closed-form
chargram model. The settings are not comparable (code vs chat, 4 candidates vs 5,
temperature 0 vs free, closed-form multinomial vs trained classifier), so the published
number is a reference point and not a target.

Result: pooled per-row accuracy 0.587 on the first draw, 0.617 pooled over draws,
against a 0.25 chance level. The signal is real but weaker per row than the published
chat-text number, and it is uneven across routes:

- Strong: Llama-3.3-70B comprehend_test 0.956 first-draw.
- Weak: DeepSeek comprehend_test 0.207 first-draw, below chance, because DeepSeek and
  Llama-3.3-70B produce near-identical bare-JSON comprehend answers (the format-cluster
  collapse already measured in Angle A). A single DeepSeek comprehend row is often
  indistinguishable from a Llama-3.3-70B row.

The honest reading: one archived row carries less producer signal than one chat
response in the published setting, and code-comprehension answers are a poorer producer
signal than chat for the near-twin pair. This is why punchmark aggregates to whole-set
rulings rather than claiming per-row identification, and it is a finding worth stating
before building anything: the instrument's per-row power is domain-dependent and the
whole-set aggregation is doing real work.

## Half 2: the model-equality-testing package (`derived/meq_attempt.json`)

The only pip-installable in-domain artifact is model-equality-testing (Gao, Liang and
Guestrin, ICLR 2025; PyPI v0.0.2, uploaded 2024-10-24, the only release). Angle B tries
to run it on this corpus. Recorded facts:

1. Packaging. `pip install` succeeds, but `import model_equality_testing` fails on
   undeclared dependencies, found only by reading successive tracebacks: first tqdm,
   then transformers. This is direct evidence that the only in-domain installable is an
   unmaintained alpha.
2. Consumption. The package has no archive reader and no notion of a route label.
   Reading gzipped JSONL, matching items across routes, unicode-encoding completions,
   padding to a common length, and assembling CompletionSample objects is all glue this
   study supplies. Two separate shape contracts had to be reverse-engineered (a 2-D
   completion tensor, and one global pad length so the two-sample path does not crash on
   a length mismatch).
3. Measurement. With that glue, the two-sample MMD (Hamming kernel, permutation
   p-values, b=200) runs to completion and behaves correctly. It fails to reject every
   same-route null pair, at p far above any conventional level with MMD at or just
   below zero, and rejects every cross-route pair at p = 0.0 with MMD well above zero
   (see `derived/meq_attempt.json` for the run's exact values; the permutation p-values
   are unseeded Monte Carlo, so they move between runs while the separation does not).
   This is an off-label use:
   the package is built for tokenized samples against a reference distribution, not raw
   archived text, so the result is reported as an observation rather than as a
   validated capability of the package.

   **Correction.** An earlier version of this study reported the opposite and described
   the package's output as invalid. That was a bug in this repository's probe script,
   which unpacked the package's `(pvalue, statistic)` return in the wrong order, so the
   two fields were swapped in every recorded result. The package was not at fault, the
   claim is withdrawn, and the numbers above come from the corrected script.

The occupancy argument does not rest on the package working badly, and it does not need
to. The package answers "are these two samples from the same distribution?" for a pair
of samples the caller must construct. It never answers "which producer", it has no
notion of a route label, it reads no archive, and it attaches no verdict to a published
number. Both halves of Angle B point the same way: the discovery literature exists and
some of it works, but nothing installable consumes an archive and returns a
producer-identity verdict, which is the gap punchmark fills.

## Reproduce

Half 1: `.venv/bin/python validation/angle_b/run.py`. Half 2 needs a scratch
environment with the package plus its undeclared deps (tqdm, transformers, torch):
`validation/angle_b/meq_probe.py`. Neither issues an API call.
