#!/usr/bin/env python3
"""Angle C collection: buy the frozen 150-row probe from the pinned routes.

Defaults to a DRY RUN that issues zero calls. Real collection needs both
``--execute`` and ``--max-usd <ceiling>``; the ceiling has no default, so
``--execute`` on its own can never authorize a spend the operator did not state.

What it does, in order:
  1. loads the gitignored credentials and prints which account each route bills;
  2. rebuilds the 150 probe prompts from the public dev seed and verifies them
     against the committed corpus (prompt_set_hash, plus per-item prompt_hash
     spot checks). A prompt mismatch aborts before any spend, because a replay
     whose prompts differ measures the prompt change, not the producer;
  3. projects each route's cost from measured prompt sizes and the observed
     output lengths of the committed June archives for the same items, refusing
     a route before its first POST if the running total would breach the ceiling;
  4. with --execute, issues k=8 sequential identical requests per item exactly as
     the original collection did (temperature 0, max_tokens 2048, two messages,
     no seed/n/stop/logprobs), writing each row as it completes so an abort never
     forces a re-buy;
  5. writes native ``<task>__<slug>.jsonl.gz`` archives under a per-provider
     directory, a window/v1 sidecar recording the real collection window and the
     provider-declared precision, and a per-item response log carrying the
     returned model string, finish reasons and usage.

The bench import below is the scoped exception documented in DESIGN.md: the
prompts must be rebuilt by the same code that built them in June. Bytecode
writing is disabled so nothing is written into the read-only checkout.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.canonical import canonical_json, sha256_file, write_text_deterministic  # noqa: E402

PROBE = ROOT / "validation" / "angle_a" / "derived" / "probe_manifest.json"
CRED = HERE / "credentials.json"
ARCHIVES = HERE / "archives"
USER_AGENT = "punchmark/0.1 (+https://github.com/KurathSec/Punchmark)"
PROMPT_SET_HASH = "36b8ffef1f3f7c79"
K_DRAWS = 8
TEMPERATURE = 0.0
MAX_TOKENS = 2048
TIMEOUT_S = 120
MAX_ATTEMPTS = 5
RETRY_BASE_S = 2.0
RETRYABLE = frozenset({429, 500, 502, 503, 504})

# Pinned prices, USD per million tokens, deliberately rounded UP so a projection
# never under-states. A route without an entry here is refused (DESIGN.md).
PRICES = {
    ("deepinfra", "meta-llama/Llama-3.3-70B-Instruct-Turbo"): 0.60,
    ("deepinfra", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"): 0.10,
    ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"): 1.20,
}

# The core purchase: the load-bearing same-weights pair plus the different-weights
# control the power gate requires. Pinned 2026-08-05, see ROUTE_AVAILABILITY.md.
ROUTES = [
    {
        "key": "deepinfra-llama70b",
        "provider": "deepinfra",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "precision": "FP8 (provider-declared, -Turbo tier)",
        "role": "load-bearing pair, DeepInfra side; also the time-drift control "
                "against the committed June archive of this slug",
    },
    {
        "key": "together-llama70b",
        "provider": "together",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "precision": "FP8 (provider-declared, -Turbo tier)",
        "role": "load-bearing pair, Together side: same slug, same declared precision",
    },
    {
        "key": "deepinfra-llama8b",
        "provider": "deepinfra",
        "model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "precision": "FP8 (provider-declared, -Turbo tier)",
        "role": "different-weights control for the power gate, paired in-window "
                "against the 70B above",
    },
]

# task name in the probe manifest -> (bench prompt builder, committed archive dir)
TASKS = {"comprehend": ("comprehend", "ladder"), "refactor_dev": ("refactor", "g3")}


def load_credentials() -> dict:
    cred = json.loads(CRED.read_text(encoding="utf-8"))["providers"]
    out = {}
    for name, spec in cred.items():
        env = spec.get("api_key_env", "")
        key = os.environ.get(env, "") if env else ""
        if not key:
            key = spec.get("api_key", "") or ""
        if key.startswith("PASTE_YOUR_"):
            key = ""
        out[name] = {
            "key": key,
            "base_url": spec["base_url"],
            "account_hint": spec.get("account_hint") or "(not stated)",
        }
    return out


def build_prompts(source: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """(task, item_key) -> (system, user), rebuilt by the corpus's own code."""
    sys.path.insert(0, str(source))
    cwd = Path.cwd()
    os.chdir(source)
    try:
        import bench.dataset as D
        import bench.models as M
        import bench.prompts as P
        import bench.tasks as T
        from src.nodes.validator import oracle

        actual = P.prompt_set_hash()
        if actual != PROMPT_SET_HASH:
            raise SystemExit(
                f"prompt-set hash mismatch: {actual} != {PROMPT_SET_HASH}. The prompt "
                "templates have changed, so a replay would measure the prompt change "
                "rather than the producer. Refusing before any spend."
            )
        manifest = json.loads(PROBE.read_text(encoding="utf-8"))["items"]
        split = D.load("dev")
        prompts: dict[tuple[str, str], tuple[str, str]] = {}
        for task, keys in manifest.items():
            builder = TASKS[task][0]
            for key in keys:
                sample, variant, profile, language = key.split("|")
                stem = T._stem_for(split, sample, variant)
                src = T._sources(split.ir(stem), profile)[language]
                rvars = list(oracle(split.program(stem)))
                if builder == "comprehend":
                    system, user = P.comprehend(language, src, rvars, 0)
                else:
                    system, user = P.refactor(language, src, rvars, 0)
                prompts[(task, key)] = (system, user)
        return prompts, M.prompt_hash
    finally:
        os.chdir(cwd)


def verify_against_committed(
    prompts: dict, prompt_hash, source: Path, n_check: int = 8
) -> int:
    """Spot-check rebuilt prompts against prompt_hash values recorded in June."""
    checked = 0
    for task, (_name, _subdir) in TASKS.items():
        finalize = source / "bench" / "out" / "subagent"
        name = "comprehend" if task == "comprehend" else "refactor"
        candidates = sorted(finalize.glob(f"{name}__*.json"))
        if not candidates:
            continue
        record = json.loads(candidates[0].read_text(encoding="utf-8"))
        by_key = {}
        for item in record.get("items", []):
            key = "|".join((item["sample"], item.get("variant", "base"),
                            item["profile"], item["language"]))
            if item.get("prompt_hash"):
                by_key[key] = item["prompt_hash"]
        for (t, key), (system, user) in prompts.items():
            if t != task or key not in by_key or checked >= n_check:
                continue
            got = prompt_hash(system, user)
            if got != by_key[key]:
                raise SystemExit(
                    f"prompt mismatch for {task} {key}: rebuilt {got} != recorded "
                    f"{by_key[key]}. Refusing before any spend."
                )
            checked += 1
    return checked


def observed_output_chars(source: Path) -> dict[str, float]:
    """Mean completion length per task, measured from the committed June archives
    for these same items. Grounds the cost projection in real data."""
    out = {}
    for task, (_, subdir) in TASKS.items():
        path = next(
            (source / "bench" / "out" / subdir).glob(f"{task}__*.jsonl.gz"), None
        )
        if path is None:
            out[task] = 2000.0
            continue
        total = n = 0
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                for text in rec.get("raw_outputs") or []:
                    total += len(text)
                    n += 1
                if n > 4000:
                    break
        out[task] = (total / n) if n else 2000.0
    return out


def project_route(route: dict, prompts: dict, out_chars: dict) -> dict:
    price = PRICES.get((route["provider"], route["model"]))
    if price is None:
        raise SystemExit(
            f"no pinned price for {route['provider']} {route['model']}; refusing "
            "(a route without a price cannot be projected against the ceiling)"
        )
    in_tok = out_tok = 0
    for (task, _key), (system, user) in prompts.items():
        # ~3.5 chars per token is conservative for code-heavy prompts
        in_tok += (len(system) + len(user)) / 3.5 * K_DRAWS
        out_tok += min(out_chars[task] / 3.5, MAX_TOKENS) * K_DRAWS
    total_tok = in_tok + out_tok
    return {
        "calls": len(prompts) * K_DRAWS,
        "est_input_tokens": int(in_tok),
        "est_output_tokens": int(out_tok),
        "usd_per_mtok": price,
        "est_usd": round(total_tok / 1_000_000 * price, 2),
    }


def post(url: str, key: str, payload: dict, counter: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(MAX_ATTEMPTS):
        req = urllib.request.Request(
            url, data=body,
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {key}", "user-agent": USER_AGENT},
        )
        try:
            counter["posts"] += 1
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE or attempt == MAX_ATTEMPTS - 1:
                raise SystemExit(
                    f"API HTTP {exc.code}: {exc.read().decode()[:300]}"
                ) from exc
            time.sleep(min(RETRY_BASE_S * 2**attempt, 60.0))
        except Exception:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            time.sleep(min(RETRY_BASE_S * 2**attempt, 60.0))
    raise SystemExit("unreachable")


def collect_route(route: dict, prompts: dict, cred: dict, counter: dict) -> dict:
    prov = cred[route["provider"]]
    slug = route["model"].replace("/", "-")
    outdir = ARCHIVES / route["provider"]
    outdir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC).isoformat()
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0}
    written = {}

    for task in TASKS:
        rows_path = outdir / f"{task}__{slug}.rows.jsonl"
        log_path = outdir / f"{task}__{slug}.responses.jsonl"
        done = set()
        if rows_path.exists():
            for line in rows_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    done.add("|".join((rec["sample"], rec["variant"],
                                       rec["profile"], rec["language"])))
        items = [(t, k) for (t, k) in prompts if t == task]
        for i, (_t, key) in enumerate(sorted(items), start=1):
            if key in done:
                continue
            system, user = prompts[(task, key)]
            sample, variant, profile, language = key.split("|")
            draws, meta = [], []
            for _ in range(K_DRAWS):
                body = post(prov["base_url"], prov["key"], {
                    "model": route["model"], "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}],
                }, counter)
                choice = (body.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                text = msg.get("content") or ""
                meta.append({
                    "returned_model": body.get("model"),
                    "finish_reason": choice.get("finish_reason"),
                    "from_reasoning_channel": bool(msg.get("reasoning_content")) and not text,
                    "usage": body.get("usage", {}),
                })
                u = body.get("usage") or {}
                usage_total["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
                usage_total["completion_tokens"] += int(u.get("completion_tokens") or 0)
                draws.append(text)
            nonempty = [d for d in draws if d.strip()]
            if not nonempty:
                raise SystemExit(
                    f"{route['key']} {task} {key}: all {K_DRAWS} draws empty; aborting "
                    "this route before spending further"
                )
            row = {"sample": sample, "variant": variant, "profile": profile,
                   "language": language, "intrinsic": {"n_ops": 0}, "tier": "A",
                   "raw_outputs": draws}
            with open(rows_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"item": key, "task": task, "draws": meta},
                                    sort_keys=True) + "\n")
            if i % 10 == 0:
                print(f"    {route['key']} {task}: {i}/{len(items)} items, "
                      f"{counter['posts']} calls so far", flush=True)

        rows = [json.loads(line) for line in
                rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows.sort(key=lambda r: (r["sample"], r["variant"], r["profile"], r["language"]))
        archive = outdir / f"{task}__{slug}.jsonl.gz"
        with gzip.GzipFile(filename="", fileobj=open(archive, "wb"), mode="wb", mtime=0) as gz:
            gz.write(("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n").encode())
        written[task] = archive
        ended = datetime.now(UTC).isoformat()
        write_text_deterministic(outdir / f"{archive.name}.window.json", canonical_json({
            "punchmark_schema": "window/v1",
            "archive": archive.name,
            "archive_sha256": sha256_file(archive),
            "route": route["model"],
            "task": task,
            "window": {"start_utc": started, "end_utc": ended},
            "collector": {
                "provider": route["provider"],
                "declared_precision": route["precision"],
                "endpoint": prov["base_url"],
                "role": route["role"],
                "k": K_DRAWS, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
                "probe": "validation/angle_a/derived/probe_manifest.json",
            },
            "declared_by": "validation/angle_c/collect.py",
        }))
        print(f"    wrote {archive.relative_to(ROOT)} ({len(rows)} rows)")
    return {"written": {k: str(v) for k, v in written.items()}, "usage": usage_total}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="/home/kureist/Spaghetti-Architect")
    ap.add_argument("--execute", action="store_true",
                    help="actually issue paid calls; requires --max-usd")
    ap.add_argument("--max-usd", type=float, default=None,
                    help="hard spend ceiling in USD; no default, must be stated")
    ap.add_argument("--routes", default="", help="comma-separated route keys (default all)")
    args = ap.parse_args()
    source = Path(args.source)

    if args.execute and args.max_usd is None:
        print("--execute requires --max-usd <ceiling>; refusing", file=sys.stderr)
        return 2

    selected = [r for r in ROUTES
                if not args.routes or r["key"] in args.routes.split(",")]
    cred = load_credentials()
    print("=" * 72)
    print("ANGLE C COLLECTION" + ("" if args.execute else "  (DRY RUN, zero calls)"))
    print("=" * 72)

    print("\nbilling:")
    for r in selected:
        p = cred.get(r["provider"], {})
        if not p.get("key"):
            print(f"  {r['key']}: NO KEY for {r['provider']}; refusing")
            return 2
        print(f"  {r['key']:22s} {r['provider']:10s} bills {p['account_hint']}"
              f"  key {p['key'][:4]}...{p['key'][-4:]}")

    print("\nfidelity gate:")
    prompts, prompt_hash = build_prompts(source)
    print(f"  prompt_set_hash {PROMPT_SET_HASH} matches")
    n = verify_against_committed(prompts, prompt_hash, source)
    print(f"  {n} per-item prompt_hash spot checks match the June records")
    print(f"  {len(prompts)} probe prompts rebuilt "
          f"({sum(1 for t,_ in prompts if t=='comprehend')} comprehend, "
          f"{sum(1 for t,_ in prompts if t=='refactor_dev')} refactor_dev)")

    out_chars = observed_output_chars(source)
    print("\nprojection (output length measured from the June archives):")
    total = 0.0
    plan = []
    for r in selected:
        proj = project_route(r, prompts, out_chars)
        plan.append((r, proj))
        total += proj["est_usd"]
        print(f"  {r['key']:22s} {proj['calls']:5d} calls  "
              f"~{(proj['est_input_tokens']+proj['est_output_tokens'])/1e6:.2f}M tok  "
              f"@ ${proj['usd_per_mtok']:.2f}/Mtok  ->  ~${proj['est_usd']:.2f}")
    print(f"  {'TOTAL':22s} {sum(p['calls'] for _, p in plan):5d} calls"
          f"{'':28s}  ->  ~${total:.2f}")
    if args.max_usd is not None:
        print(f"  ceiling ${args.max_usd:.2f}  ->  "
              f"{'WITHIN' if total <= args.max_usd else 'EXCEEDS, would refuse'}")

    if not args.execute:
        print("\nDry run only. No calls were issued and nothing was billed.")
        print("To collect:  --execute --max-usd <ceiling>")
        return 0

    if total > args.max_usd:
        print(f"\nprojected ${total:.2f} exceeds ceiling ${args.max_usd:.2f}; refusing")
        return 1

    counter = {"posts": 0}
    spent = 0.0
    print("\ncollecting:")
    for r, proj in plan:
        if spent + proj["est_usd"] > args.max_usd:
            print(f"  stopping before {r['key']}: would breach the ceiling")
            break
        print(f"  {r['key']} ({r['model']} via {r['provider']})")
        result = collect_route(r, prompts, cred, counter)
        u = result["usage"]
        actual = (u["prompt_tokens"] + u["completion_tokens"]) / 1e6 * proj["usd_per_mtok"]
        spent += actual if actual else proj["est_usd"]
        print(f"    usage {u['prompt_tokens']}+{u['completion_tokens']} tok, "
              f"~${actual:.2f}; running total ~${spent:.2f} of ${args.max_usd:.2f}")
    print(f"\ndone: {counter['posts']} calls, ~${spent:.2f} spent "
          f"(ceiling ${args.max_usd:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
