"""Leak scan: run on everything you are about to publish. It must report zero hits.

    python leakscan.py                       # scans out/
    python leakscan.py out/Grok --deny work/denylist.txt

Scans every file under the given folders (HTML pages, JSON, Markdown, and the text of .docx). The grader values of each
task (the numbers and strings inside the expected, reference, golden, definition, details and rubric fields of every grader
output saved under work/<key>/raw/graders/, or --graders DIR) are looked for only in text that belongs to that task: the
file T07.json, the page's prompt of T07, a card of a T07 run. Checks:
  numbers   4+ digit numbers from the task's grader fields
  strings   strings of 13+ characters (with a space or a digit) from the task's grader fields (all tasks, any text)
  ids       task, run and evaluation ids from work/<key>/selection.json and tasks.json
  urls      any URL other than Google Fonts and the ones given with --allow-url
  emails    any email address
  dashes    em and en dashes (pages, Doc and Markdown only: step detail is the run as recorded)
  words     the word "simulated" (pages, Doc and Markdown only; the corpus is real operational data), and every line of
            the --deny file(s) (everywhere). The deny file is yours: one name per line, kept in work/ (gitignored). Put the
            company's name and its counterparties' names in it.
Exit code 1 when anything is found.
"""

import argparse
import collections
import glob
import json
import os
import re
import sys
import zipfile

from cbr import scrub as SC
from cbr.common import HERE, KIT, OUT, WORK, jload

FONTS = ("fonts.g",)
ALIAS = re.compile(r"^(T\d\d)(?:-|$)")
DASHES = (chr(0x2014), chr(0x2013))


def segs(o, alias, out):
    """(alias, text) for every key and string in a JSON value; the alias follows the nearest T## key or alias field."""
    if isinstance(o, dict):
        a = alias
        if isinstance(o.get("alias"), str) and ALIAS.match(o["alias"]):
            a = ALIAS.match(o["alias"]).group(1)
        for k, v in o.items():
            if k in ("title", "cat") and isinstance(v, str):
                out.append(
                    ("__prompt", v)
                )  # generic task titles are published by design
                continue
            m = ALIAS.match(str(k))
            ka = m.group(1) if m else a
            out.append((ka, str(k)))
            segs(v, ka, out)
    elif isinstance(o, list):
        for v in o:
            segs(v, alias, out)
    elif isinstance(o, str):
        out.append((alias, o))
    return out


def segments(path):
    """Returns (kind, [(alias, text)]) with kind 'data' (step detail and timelines) or 'authored'."""
    base = os.path.basename(path)
    if path.endswith(".docx"):
        x = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "replace")
        return "authored", [(None, re.sub(r"<[^>]+>", " ", x))]
    raw = open(path, encoding="utf-8", errors="replace").read()
    m = re.match(r"(T\d\d)\.json$", base)
    if path.endswith(".json"):
        try:
            j = json.loads(raw)
        except Exception:
            return "authored", [(None, raw)]
        kind = "data" if re.search(r"data[\\/](full|traces)[\\/]", path) else "authored"
        return kind, segs(j, m.group(1) if m else None, [])
    if path.endswith(".html"):
        parts = []
        m = re.search(r"const D=(\{.*?\});\nconst S=D\.subject", raw, re.S)
        if m:
            blob = json.loads(m.group(1))
            # the task prompts are what the solving model was given: they cannot hold an answer, so value checks skip them
            prompts = blob.pop("prompts", {}) or {}
            parts = segs(blob, None, []) + [("__prompt", t) for t in prompts.values()]
            raw = raw[: m.start()] + raw[m.end() :]
        m2 = re.search(r"window\.__TR=(\{.*?\});</script>", raw, re.S)
        if m2:
            parts += [(a, t) for a, t in segs(json.loads(m2.group(1)), None, [])]
            raw = raw[: m2.start()] + raw[m2.end() :]
        return "authored", parts + [(None, raw)]
    return "authored", [(None, raw)]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("paths", nargs="*", default=[OUT])
    ap.add_argument(
        "--graders",
        action="append",
        default=[],
        help="extra folder of grader output files named <run_id>.json",
    )
    ap.add_argument(
        "--deny",
        action="append",
        default=[],
        help="file of names that must not appear, one per line",
    )
    ap.add_argument("--allow-url", action="append", default=[])
    a = ap.parse_args()
    # run id -> alias, from the selections
    run_alias, ids = {}, set()
    for sel in glob.glob(os.path.join(WORK, "*", "selection.json")):
        s = jload(sel)
        for r in s["runs"] + s["long"]:
            run_alias[str(r["run_id"])] = r["alias"]
            ids.update(str(r[k]) for k in ("run_id", "eval_id", "task_id") if r.get(k))
    task_alias = {}
    for t in jload(os.path.join(KIT, "tasks.json")):
        ids.update([str(t["task"]), str(t["long"])])
    gfiles = glob.glob(os.path.join(WORK, "*", "raw", "graders", "*.json"))
    for d in a.graders:
        gfiles += glob.glob(os.path.join(d, "*"))
    vals = collections.defaultdict(lambda: (set(), set()))
    for g in gfiles:
        al = run_alias.get(os.path.splitext(os.path.basename(g))[0])
        try:
            c = SC.grader_obj(open(g, encoding="utf-8").read())
        except Exception:
            continue
        if c is None or al is None:
            continue
        n, s = vals[al]
        SC._walk(c, False, n, s)
    vals, allstr = SC.scan_values(dict(vals))
    nstr = sum(len(n) + len(s) for n, s in vals.values())
    deny = []
    for f in a.deny:
        deny += [x.strip() for x in open(f, encoding="utf-8") if x.strip()]
    if not gfiles:
        print(
            "WARNING: no grader files under work/*/raw/graders/. The number and string checks cannot run; fetch a model first."
        )
    files = []
    for p in a.paths:
        if os.path.isdir(p):
            files += [
                f
                for f in glob.glob(os.path.join(p, "**", "*"), recursive=True)
                if os.path.isfile(f)
                and f.endswith(
                    (".html", ".json", ".md", ".docx", ".txt", ".js", ".css")
                )
            ]
        elif os.path.isfile(p):
            files.append(p)
    hits, detail = collections.Counter(), []
    for f in sorted(files):
        kind, sg = segments(f)
        for al, t in sg:
            if not t:
                continue
            if al in vals:
                nums, strs = vals[al]
                found = set(
                    re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d])", t.replace(",", ""))
                )
                for n in nums & found:
                    hits["number"] += 1
                    detail.append((f, "number", "%s in %s" % (n, al)))
            elif al == "__prompt":
                strs = set()
            else:
                strs = allstr
            for s in strs:
                if s in t:
                    hits["string"] += 1
                    detail.append((f, "string", s))
            for i in set(re.findall(r"(?<![\d.])\d{5,7}(?!\d)", t)) & ids:
                hits["id"] += 1
                detail.append((f, "id", i))
            for u in re.findall(r"https?://[^\s\"'<>)]+", t):
                if not any(x in u for x in FONTS + tuple(a.allow_url)):
                    hits["url"] += 1
                    detail.append((f, "url", u[:70]))
            for e in re.findall(r"[\w.+-]+@[\w-]+\.\w+", t):
                hits["email"] += 1
                detail.append((f, "email", e))
            if kind == "authored":
                for ch in DASHES:
                    if ch in t:
                        hits["dash"] += 1
                        detail.append((f, "dash", "U+%04X" % ord(ch)))
                if re.search("simulated", t, re.I):
                    hits["word"] += 1
                    detail.append((f, "word", "simulated"))
            for w in deny:
                if re.search(re.escape(w), t, re.I):
                    hits["word"] += 1
                    detail.append((f, "word", "(deny list entry)"))
    print(
        "files scanned %d; grader files %d for %d tasks (%d values); ids %d; deny entries %d"
        % (len(files), len(gfiles), len(vals), nstr, len(ids), len(deny))
    )
    print("HITS:", dict(hits) if hits else "0")
    for d in detail[: int(os.environ.get("LEAK_SHOW", "60"))]:
        print(" ", os.path.relpath(d[0], HERE), d[1], d[2][:80])
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
