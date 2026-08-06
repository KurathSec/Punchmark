#!/usr/bin/env python3
"""Verify the Angle C credentials without spending anything.

Reads validation/angle_c/credentials.json (gitignored), then for each provider
that has a key issues ONE request to the models endpoint, which is free on both
DeepInfra and Together and bills no tokens. It never calls chat/completions, so
running this cannot cost money.

Prints, per provider: whether a key was found and where it came from, whether
the endpoint accepts it, and whether the routes Angle C plans to buy are listed
in that provider's catalogue right now. Purchasability is the recorded project
risk, so a route that has disappeared should be found here rather than halfway
through a paid run.

Usage:  python3 validation/angle_c/check_credentials.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CRED = HERE / "credentials.json"
PLACEHOLDER = "PASTE_YOUR_"

# The routes the load-bearing core needs, per provider (DESIGN.md, routes 1-3).
PLANNED = {
    "together": ["meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    "deepinfra": [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        # The June corpus used meta-llama/Meta-Llama-3.1-8B-Instruct, which DeepInfra
        # no longer serves (see ROUTE_AVAILABILITY.md). The in-window different-weights
        # control therefore uses the Turbo variant, which is what is purchasable now.
        "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    ],
}
# Routes the committed June 2026 corpus was collected from, checked for continued
# availability because their disappearance is the hazard this study is about.
COMMITTED_JUNE = [
    "deepseek-ai/DeepSeek-V4-Flash",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
]
MODELS_URL = {
    "together": "https://api.together.xyz/v1/models",
    "deepinfra": "https://api.deepinfra.com/v1/openai/models",
}
# Together sits behind Cloudflare, which rejects urllib's default User-Agent with
# error 1010 ("blocked based on your browser's signature") -- a 403 that looks like
# an auth failure but is not. Every request this project makes names itself.
USER_AGENT = "punchmark/0.1 (+https://github.com/KurathSec/Punchmark)"


def resolve_key(name: str, spec: dict) -> tuple[str, str]:
    """(key, where it came from). The environment wins over the file."""
    env_name = spec.get("api_key_env", "")
    env_val = os.environ.get(env_name, "") if env_name else ""
    if env_val:
        return env_val, f"environment variable {env_name}"
    key = spec.get("api_key", "") or ""
    if key.startswith(PLACEHOLDER) or not key:
        return "", "not set"
    return key, f"credentials.json ({name}.api_key)"


def list_models(url: str, key: str) -> tuple[bool, list[str], str]:
    req = urllib.request.Request(
        url,
        headers={
            "authorization": f"Bearer {key}",
            "accept": "application/json",
            "user-agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, [], f"HTTP {exc.code} ({exc.reason})"
    except Exception as exc:  # network, DNS, TLS
        return False, [], f"{type(exc).__name__}: {exc}"
    rows = body.get("data", body) if isinstance(body, dict) else body
    ids: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                model_id = row.get("id") or row.get("model_name") or ""
                if model_id:
                    ids.append(str(model_id))
    return True, ids, "ok"


def main() -> int:
    if not CRED.exists():
        print(f"no credentials file at {CRED}", file=sys.stderr)
        print("copy credentials.example.json to credentials.json and fill it in",
              file=sys.stderr)
        return 2
    try:
        cred = json.loads(CRED.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"{CRED}: not valid JSON ({exc.msg}) at line {exc.lineno}", file=sys.stderr)
        return 2
    providers = cred.get("providers", {})
    if not providers:
        print(f"{CRED}: no 'providers' section", file=sys.stderr)
        return 2

    print(f"credentials file: {CRED}")
    print(f"file mode: {oct(CRED.stat().st_mode & 0o777)} (0o600 means only you can read it)")
    print()
    problems = 0
    for name in ("together", "deepinfra"):
        spec = providers.get(name)
        print(f"[{name}]")
        if not spec:
            print("  no entry in credentials.json")
            problems += 1
            print()
            continue
        key, source = resolve_key(name, spec)
        hint = spec.get("account_hint") or "(not stated)"
        print(f"  key source : {source}")
        print(f"  bills      : {hint}")
        if not key:
            print("  status     : NO KEY YET, nothing checked")
            problems += 1
            print()
            continue
        print(f"  key        : {key[:4]}...{key[-4:]} ({len(key)} chars)")
        ok, ids, detail = list_models(MODELS_URL[name], key)
        if not ok:
            print(f"  status     : endpoint rejected the key or was unreachable: {detail}")
            problems += 1
            print()
            continue
        print(f"  status     : accepted, {len(ids)} models listed")
        if name == "deepinfra":
            print("  committed June 2026 routes, still purchasable?")
            for slug in COMMITTED_JUNE:
                state = "yes" if slug in ids else "NO LONGER SERVED"
                print(f"    {state:17s} {slug}")
        for wanted in PLANNED[name]:
            exact = wanted in ids
            loose = [m for m in ids if m.lower() == wanted.lower()]
            mark = "found" if (exact or loose) else "NOT LISTED"
            print(f"  route      : {wanted}  -> {mark}")
            if not (exact or loose):
                near = [m for m in ids if wanted.split("/")[-1][:18].lower() in m.lower()]
                if near:
                    print(f"               closest listed: {', '.join(near[:3])}")
                problems += 1
        print()

    if problems:
        print(f"{problems} thing(s) need attention before collection can be planned.")
        return 1
    print("all planned routes are purchasable and both keys work. No tokens were spent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
