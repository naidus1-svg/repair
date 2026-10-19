"""Register a new model in data/models.json so the builders know its label and colour.

    python add_model.py --key Grok --label "Grok 4.7" --id 65

--key is the short name used in run keys and file names (letters and digits, no spaces). It must be new.
The colour is taken from a fixed palette in the order models are added.
"""

import argparse
import json
import os
import re

from cbr.common import DATA

PALETTE = [
    ("#b0577a", "#d98aa8"),
    ("#3f8f9a", "#79c0ca"),
    ("#8f8a3f", "#c4bf6f"),
    ("#7a6a5c", "#b3a395"),
    ("#4a6fd0", "#8fa8ec"),
    ("#c0504d", "#e58f8c"),
]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--key", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--id", type=int, help="Data OS model id")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", a.key):
        raise SystemExit(
            "--key must be letters and digits only, starting with a letter"
        )
    p = os.path.join(DATA, "models.json")
    d = json.load(open(p, encoding="utf-8"))
    if any(m["key"].lower() == a.key.lower() for m in d["models"]):
        raise SystemExit("%s is already in data/models.json" % a.key)
    col = (
        PALETTE[(len(d["models"]) - 4) % len(PALETTE)]
        if len(d["models"]) >= 4
        else PALETTE[0]
    )
    d["models"].append(
        {
            "key": a.key,
            "label": a.label,
            "dataos_id": a.id,
            "color": col[0],
            "color_dark": col[1],
            "saved": False,
        }
    )
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=2)
        fh.write("\n")
    print("added", a.key, "(%s)" % a.label, "colour", col[0])


if __name__ == "__main__":
    main()
