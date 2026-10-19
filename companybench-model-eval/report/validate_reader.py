"""Check the reader files of a subject model: right shapes, run keys that exist, no dashes.

    python validate_reader.py --subject Grok

Reads data/reader/<subject>/*.json (see data/reader/SCHEMA.md) and the runs of every model. Prints each problem and exits
1 if there is any. Run leakscan.py afterwards: this script does not look at grader values.
"""

import argparse
import os
import sys

from cbr import views
from cbr.common import DATA, jload

DASH = (chr(0x2014), chr(0x2013))


def strings(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)
    elif isinstance(o, str):
        yield o


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--subject", required=True)
    a = ap.parse_args()
    d = os.path.join(DATA, "reader", a.subject)
    if not os.path.isdir(d):
        raise SystemExit("No folder %s" % d)
    D = views.load(a.subject)
    keys = {r["key"] for r in D["runs"]}
    aliases = set(D["tasks"])
    bad = []
    files = {
        n: jload(os.path.join(d, n + ".json"), default=None)
        for n in ("cards", "rcards", "mx", "sbs", "walk", "notes", "stories")
    }
    for n, v in files.items():
        if v is None:
            continue
        if any(ch in s for s in strings(v) for ch in DASH):
            bad.append("%s.json contains an em or en dash" % n)
    for n in ("cards", "rcards", "walk", "notes"):
        for k in files[n] or {}:
            if k not in keys:
                bad.append("%s.json: unknown run key %s" % (n, k))
    for k, c in (files["cards"] or {}).items():
        for f in ("mode", "grader", "shows"):
            if f not in c:
                bad.append("cards.json: %s has no %s" % (k, f))
    modes = {
        c.get("mode")
        for c in list((files["cards"] or {}).values())
        + list((files["rcards"] or {}).values())
    }
    mx = files["mx"] or {}
    for m in mx.get("modes", []):
        if m.get("mode") not in modes:
            bad.append("mx.json: mode %r is not used by any card" % m.get("mode"))
        for e in m.get("examples", []):
            if e.get("key") not in keys:
                bad.append("mx.json: unknown example run %s" % e.get("key"))
    for k in mx.get("notes", {}):
        if k not in keys:
            bad.append("mx.json notes: unknown run key %s" % k)
    for t in (files["sbs"] or {}).get("tasks", []):
        for f in ("alias", "side", "argon_key", "peer_key", "argon", "peer", "why"):
            if f not in t:
                bad.append("sbs.json: a task has no %s" % f)
        for f in ("argon_key", "peer_key"):
            if t.get(f) and t[f] not in keys:
                bad.append("sbs.json: unknown run key %s" % t[f])
        if t.get("alias") not in aliases:
            bad.append("sbs.json: unknown task %s" % t.get("alias"))
    for s in files["stories"] or []:
        if s[0] not in keys:
            bad.append("stories.json: unknown run key %s" % s[0])
    for b in bad[:50]:
        print(b)
    print("%d problem(s)" % len(bad) if bad else "reader files OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
