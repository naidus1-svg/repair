"""Check that the pipeline reproduces the published Gemini report when Argon is run through it as if it were a new model.

    python fetch.py --key Argon --main repro/argon_main.csv --long repro/argon_long.csv
    python analyze.py --key Argon
    python check_repro.py

Passes when the fresh analysis of Argon gives the published numbers (80 minute view 55 of 120 full marks; 5 hour view
73 of 117 on the 39 tasks whose reruns finished) and every counted run matches the saved copy in data/models/Argon
(score, minutes, tokens, cost, turns, largest turn).
"""

import os
import sys

from cbr import views
from cbr.common import SAVED, WORK, jload

PUBLISHED = {"80": (55, 120), "same": (73, 117)}
FIELDS = (
    "reward",
    "minutes",
    "agent_min",
    "tool_calls",
    "in_tok",
    "out_tok",
    "cache_tok",
    "cost",
    "env_cost",
    "turns",
    "max_turn_tokens",
    "turns_8k",
    "timeout",
)


def main():
    fresh = os.path.join(WORK, "models", "Argon", "runs.json")
    if not os.path.exists(fresh):
        raise SystemExit(
            "No fresh Argon analysis found. Run fetch.py and analyze.py for Argon first (see the docstring)."
        )
    ok = True
    D = views.load("Argon")
    for v, (full, n) in PUBLISHED.items():
        got = (D["V"][v]["Argon"]["full"], D["V"][v]["Argon"]["n"])
        good = got == (full, n)
        ok &= good
        print(
            "%-5s Argon full marks %d of %d (published %d of %d): %s"
            % (v, got[0], got[1], full, n, "OK" if good else "MISMATCH")
        )
    new = {r["key"]: r for r in jload(fresh)}
    old = {r["key"]: r for r in jload(os.path.join(SAVED, "Argon", "runs.json"))}
    bad = []
    for k in sorted(set(new) | set(old)):
        if k not in new or k not in old:
            bad.append((k, "missing", None))
            continue
        for f in FIELDS:
            a, b = new[k].get(f), old[k].get(f)
            if a != b and not (
                isinstance(a, (int, float))
                and isinstance(b, (int, float))
                and abs(a - b) < 1e-6
            ):
                bad.append((k, f, (a, b)))
    print(
        "runs compared: %d fresh, %d saved, %d differences"
        % (len(new), len(old), len(bad))
    )
    for b in bad[:10]:
        print("  ", b)
    ok &= not bad
    print("REPRODUCES THE PUBLISHED NUMBERS" if ok else "DOES NOT REPRODUCE")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
