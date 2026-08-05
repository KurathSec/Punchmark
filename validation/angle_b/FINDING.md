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
   p-values) produces invalid output on this off-label input: p-values outside [0, 1]
   (negative for same-route null pairs, above 1 for a cross-route pair), and an inverted
   ordering where same-route null pairs score a large statistic while cross-route pairs
   collapse to 0.0. No valid distributional verdict can be extracted. The package is
   built for tokenized samples with a reference distribution, not raw archived text, and
   forcing an archive through it yields nonsense rather than an answer.

The package answers "same distribution?" for a pair of samples the user must construct;
it never answers "which producer" and never attaches a verdict to a published number.
Both halves of Angle B point the same way: the discovery literature exists, but nothing
installable consumes an archive and returns a producer-identity verdict, which is the
gap punchmark fills.

## Reproduce

Half 1: `.venv/bin/python validation/angle_b/run.py`. Half 2 needs a scratch
environment with the package plus its undeclared deps (tqdm, transformers, torch):
`validation/angle_b/meq_probe.py`. Neither issues an API call.
