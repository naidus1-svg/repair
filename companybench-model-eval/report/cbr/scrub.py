"""Masking of step text before it is published, and the grader values the leak scan checks against.

For each task, every number and string the grader holds as expected or reference (from that task's grader output),
plus emails, URLs and capitalised first-and-last name pairs, is replaced with [value], [email], [url] or [name].
When no readable grader values exist for a task (or --strict is given), every number of 3+ digits and every decimal
is masked instead. Run leakscan.py on the finished site: it must report zero hits.
"""

import json
import re

KEYS = (
    "expected",
    "expected_value",
    "reference",
    "golden",
    "definition",
    "details",
    "rubric",
    "target",
    "answer",
)
KEEPWORDS = set(
    "Slack Jira Confluence Drive Google Sheet Sheets Excel Python SQL Postgres Freshdesk Gmail Email Ticket Tickets Report Summary Analysis Plan Total Count Status Account Accounts Card Cards Bill Bills Transfer Transfers Fee Fees Audit New The This That Wiki Page Pages Table Tables Next Step Final Answer Data User Users Customer Customers Support Team Channel Message Messages Comment Comments Issue Issues Project Policy Process Review Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August September October November December".split()
)
NAME = re.compile(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b")


def grader_obj(g):
    """The grader JSON from an output-file response: {'content': '<text>'} where the text may open with check lines."""
    if g is None:
        return None
    try:
        j = json.loads(g) if isinstance(g, str) else g
    except Exception:
        return None
    c = j.get("content") if isinstance(j, dict) and "content" in j else j
    if isinstance(c, str):
        for start in (0, c.find("\n{") + 1 if "\n{" in c else -1):
            if start < 0:
                continue
            try:
                return json.loads(c[start:])
            except Exception:
                pass
        return None
    return c


def _walk(o, keep, nums, strs):
    if isinstance(o, dict):
        for k, v in o.items():
            _walk(v, keep or k in KEYS, nums, strs)
    elif isinstance(o, list):
        for v in o:
            _walk(v, keep, nums, strs)
    elif keep and o is not None:
        s = str(o)
        for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s):
            d = n.replace(",", "")
            if len(re.sub(r"\D", "", d)) >= 2:
                nums.add(d)
        for q in re.findall(r"'([^']{6,80})'|\"([^\"]{6,80})\"", s):
            strs.add((q[0] or q[1]).strip())
        if 6 <= len(s) <= 80 and not re.fullmatch(r"[\d.,\s%$-]+", s):
            strs.add(s.strip())


def alias_values(work_dir, extra_dirs=()):
    """{alias: (numbers, strings longest first)} from every grader output saved under work/<key>/raw/graders/ (all models,
    all runs of the task), the same extraction the step-detail masking uses."""
    import collections
    import glob
    import os

    from .common import jload

    gs = collections.defaultdict(list)
    for sel in glob.glob(os.path.join(work_dir, "*", "selection.json")):
        s = jload(sel)
        d = os.path.join(os.path.dirname(sel), "raw", "graders")
        for r in s["runs"] + s["long"]:
            p = os.path.join(d, "%d.json" % r["run_id"])
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    gs[r["alias"]].append(fh.read())
    return {al: task_values(g, limit=None) for al, g in gs.items()}


ALIAS = re.compile(r"^(T\d\d)(?:-|$)")


def known_ids(work_dir):
    """Task, run and evaluation ids of every selection under work/ plus the 40 tasks and their 5 hour copies."""
    import glob
    import os

    from .common import KIT, jload

    ids = set()
    for sel in glob.glob(os.path.join(work_dir, "*", "selection.json")):
        s = jload(sel)
        for r in s["runs"] + s["long"]:
            ids.update(str(r[k]) for k in ("run_id", "eval_id", "task_id") if r.get(k))
    for t in jload(os.path.join(KIT, "tasks.json")):
        ids.update([str(t["task"]), str(t["long"])])
    return {i for i in ids if 5 <= len(i) <= 7}


def scan_values(vals):
    """The values the leak scan looks for: numbers of 4+ digits and strings of 13+ characters (with a space or a digit),
    per task, plus the union of all strings. Input: the output of alias_values()."""
    out = {}
    for al, (n, s) in vals.items():
        n = {x for x in n if len(re.sub(r"\D", "", x)) > 3}
        s = {x.strip() for x in s if len(x) > 12 and (" " in x or re.search(r"\d", x))}
        out[al] = (n, s)
    allstr = set().union(*[v[1] for v in out.values()]) if out else set()
    return out, allstr


def scrub_light(text, nums, strs):
    """Replace the scan's strings and numbers in free text. Used on written reader text, where small numbers (step
    numbers, counts) must stay readable."""
    for s in sorted(strs, key=len, reverse=True):
        if s in text:
            text = text.replace(s, "[value]")
    if nums:
        text = re.sub(
            r"(?<![\d.])\d[\d,]*(?:\.\d+)?(?!\d)",
            lambda m: "[value]" if m.group(0).replace(",", "") in nums else m.group(0),
            text,
        )
    return text


def scrub_tree(o, sv, allstr, alias=None):
    """scrub_light on every string of a JSON value; the task comes from the nearest T## key or alias field."""
    if isinstance(o, dict):
        a = alias
        if isinstance(o.get("alias"), str) and ALIAS.match(o["alias"]):
            a = ALIAS.match(o["alias"]).group(1)
        out = {}
        for k, v in o.items():
            m = ALIAS.match(str(k))
            ka = m.group(1) if m else a
            out[k] = scrub_tree(v, sv, allstr, ka)
        return out
    if isinstance(o, list):
        return [scrub_tree(v, sv, allstr, alias) for v in o]
    if isinstance(o, str):
        nums, strs = sv.get(alias, (set(), allstr))
        return scrub_light(o, nums, strs)
    return o


def task_values(graders, limit=3):
    """graders: list of raw output-file responses for one task. Returns (set of numbers, strings longest first)."""
    nums, strs = set(), set()
    for g in (graders if limit is None else graders[:limit]):
        c = grader_obj(g)
        if c is not None:
            _walk(c, False, nums, strs)
    strs = {s for s in strs if len(s) >= 6 and not re.fullmatch(r"[a-z_]+", s)}
    return nums, sorted(strs, key=len, reverse=True)


def scrub(text, nums, strs, strict=False):
    if not text:
        return ""
    for s in strs:
        if s in text:
            text = text.replace(s, "[value]")
    text = re.sub(r"https?://\S+", "[url]", text)
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[email]", text)
    strict = strict or (not nums and not strs)

    def num(m):
        d = m.group(0).replace(",", "")
        if strict:
            return (
                "[value]"
                if (len(re.sub(r"\D", "", d)) >= 3 or "." in d)
                else m.group(0)
            )
        return "[value]" if d in nums else m.group(0)

    text = re.sub(r"(?<![\d.])\d[\d,]*(?:\.\d+)?(?!\d)", num, text)
    return NAME.sub(
        lambda m: (
            m.group(0)
            if (m.group(1) in KEEPWORDS or m.group(2) in KEEPWORDS)
            else "[name]"
        ),
        text,
    )
