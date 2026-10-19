"""Paths, JSON helpers, the model registry and the run-key convention."""

import csv
import gzip
import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../report
DATA = os.path.join(HERE, "data")
SAVED = os.path.join(DATA, "models")  # committed results of finished models
WORK = os.path.join(HERE, "work")  # raw downloads and fresh analysis; gitignored
OUT = os.path.join(HERE, "out")  # built site and Doc; gitignored
FULL = 0.9999  # "full marks" means a reward of at least this
KIT = os.path.dirname(HERE)  # .../companybench-model-eval


def ts(x):
    """ISO timestamp (with Z) to epoch seconds."""
    return datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp()


def jload(path, default=None):
    """Read JSON (plain or .gz). A missing file returns default."""
    if not os.path.exists(path):
        if default is not None:
            return default
        raise FileNotFoundError(path)
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def jsave(path, obj, indent=None):
    """Write JSON (plain or .gz), compact unless indent is given."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    op = gzip.open if path.endswith(".gz") else open
    kw = {"indent": indent} if indent else {"separators": (",", ":")}
    with op(path, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, **kw)


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def registry():
    """data/models.json: ordered list of models. The first entries are the saved baselines."""
    return jload(os.path.join(DATA, "models.json"))["models"]


def reg_entry(key):
    for m in registry():
        if m["key"] == key:
            return m
    raise KeyError(
        "model %r is not in data/models.json; add it first (README step 2)" % key
    )


def model_dir(key):
    """Where a model's analysed results live: work/models/<key> if fresh, else the saved copy."""
    w = os.path.join(WORK, "models", key)
    if os.path.exists(os.path.join(w, "runs.json")):
        return w
    return os.path.join(SAVED, key)


def run_key(alias, model_key, cell, long=False):
    return "%s-%s-%d%s" % (alias, model_key.lower(), int(cell), "L" if long else "")
