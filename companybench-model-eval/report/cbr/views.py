"""Assemble the data of a report for N models: the four views, the matrix, the roll-ups.

Views:
  80     every model, its 3 counted runs per task, one 80 minute limit
  swap   a run that timed out at 80 minutes is replaced by its 5 hour rerun, where one was run and scored
  same   swap, restricted to the tasks where every rerun of every model finished (a task with an unscored rerun is
         dropped for ALL models, so every model is scored on the same tasks)
  sens0  swap over all 40 tasks, a rerun that did not finish scored as 0
"""

import collections
import os
import statistics as st

from . import scrub
from .common import DATA, FULL, WORK, jload, model_dir, registry


def order(subject, keys=None):
    reg = {m["key"]: m for m in registry()}
    ks = list(keys) if keys else [m["key"] for m in registry()]
    if subject not in ks:
        ks.append(subject)
    ks = [k for k in ks if k != subject]
    return [subject] + ks, reg


def agg(rs, with_cost=True):
    n = len(rs)
    if not n:
        return dict(n=0)
    mins = sorted(r["minutes"] for r in rs)
    a = dict(
        n=n,
        full=sum(1 for r in rs if r["reward"] >= FULL),
        mean=round(sum(r["reward"] for r in rs) / n, 3),
        tool_calls=round(sum(r["tool_calls"] for r in rs) / n, 1),
        turns=round(sum(r["turns"] for r in rs) / n, 1),
        minutes=round(sum(r["minutes"] for r in rs) / n, 1),
        agent_min_median=round(st.median(r["agent_min"] for r in rs), 1),
        in_tok=round(sum(r["in_tok"] for r in rs) / n),
        out_tok=round(sum(r["out_tok"] for r in rs) / n),
        cost=round(sum(r["cost"] for r in rs) / n, 2),
        timeouts=sum(1 for r in rs if r.get("timeout") and r["view"] == "80"),
        p90_min=round(mins[max(0, int(0.9 * n) - 1)], 1),
        partial=sum(1 for r in rs if 0 < r["reward"] < FULL),
        zero=sum(1 for r in rs if r["reward"] <= 0),
    )
    tot = sum(r["cost"] for r in rs)
    a["cost_per_full"] = round(tot / a["full"], 2) if a["full"] else None
    return a


def load(subject, keys=None):
    ks, reg = order(subject, keys)
    tasks = jload(os.path.join(DATA, "tasks.json"))
    alias = sorted(tasks)
    runs, meta, why, lt, modes, ltr = {}, {}, {}, {}, {}, {}
    for k in ks:
        d = model_dir(k)
        if not os.path.exists(os.path.join(d, "runs.json")):
            raise SystemExit(
                "No results for %s. Run fetch.py and analyze.py for it first, or save its folder to data/models/%s/."
                % (k, k)
            )
        runs[k] = jload(os.path.join(d, "runs.json"))
        meta[k] = jload(os.path.join(d, "meta.json"), default={})
        why.update(jload(os.path.join(d, "why.json"), default={}))
        lt[k] = jload(os.path.join(d, "longturns.json"), default={})
        modes.update(jload(os.path.join(d, "modes.json"), default={}))
        ltr.update(jload(os.path.join(d, "longturn_runs.json"), default={}))
    allruns = [r for k in ks for r in runs[k]]
    long_of = {r["replaces"]: r for r in allruns if r["view"] == "long"}
    pend = sorted({p for k in ks for p in (meta[k].get("pending_keys") or [])})
    drop = sorted({p.split("-")[0] for p in pend})
    keep = [a for a in alias if a not in drop]

    def view_runs(m, v):
        out = []
        for r in runs[m]:
            if r["view"] != "80":
                continue
            out.append(long_of.get(r["key"], r) if v == "swap" else r)
        return out

    V = {
        "80": {m: agg(view_runs(m, "80")) for m in ks},
        "swap": {m: agg(view_runs(m, "swap")) for m in ks},
        "same": {
            m: agg([r for r in view_runs(m, "swap") if r["alias"] in keep]) for m in ks
        },
        "sens0": {
            m: agg(
                [
                    dict(r, reward=0.0) if r["key"] in pend else r
                    for r in view_runs(m, "swap")
                ]
            )
            for m in ks
        },
    }
    by = collections.defaultdict(list)
    for r in allruns:
        by[(r["alias"], r["model"], r["view"])].append(r)
    matrix = []
    for a in alias:
        row = {
            "alias": a,
            "title": tasks[a]["title"],
            "cat": tasks[a].get("cat", ""),
            "cells": {},
            "long": {},
        }
        for m in ks:
            rs = sorted(by[(a, m, "80")], key=lambda r: r["cell"])
            row["cells"][m] = [
                [r["key"], round(r["reward"], 3), bool(r.get("timeout"))] for r in rs
            ]
            if any(r["key"] in long_of for r in rs):
                row["long"][m] = [
                    (
                        [
                            long_of[r["key"]]["key"],
                            round(long_of[r["key"]]["reward"], 3),
                        ]
                        if r["key"] in long_of
                        else None
                    )
                    for r in rs
                ]
        matrix.append(row)
    lsum = {}
    for m in ks:
        lr = [r for r in runs[m] if r["view"] == "long"]
        if not lr:
            continue
        orig = {r["key"]: r for r in runs[m] if r["view"] == "80"}
        lsum[m] = dict(
            n=len(lr),
            full=sum(1 for r in lr if r["reward"] >= FULL),
            mean=round(sum(r["reward"] for r in lr) / len(lr), 3),
            agent_median=round(st.median(r["agent_min"] for r in lr), 1),
            over80=sum(1 for r in lr if r["agent_min"] > 80),
            max_agent=round(max(r["agent_min"] for r in lr), 1),
            turns_median=st.median(r["turns"] for r in lr),
            turns8k=sum(r["turns_8k"] for r in lr),
            turns_all=sum(r["turns"] for r in lr),
            orig_turns8k=sum(orig[r["replaces"]]["turns_8k"] for r in lr),
            orig_turns_all=sum(orig[r["replaces"]]["turns"] for r in lr),
            orig_turns_median=st.median(orig[r["replaces"]]["turns"] for r in lr),
            slots=meta[m].get("slots"),
            pending=meta[m].get("pending", 0),
        )
    keepf = (
        "key",
        "alias",
        "model",
        "cell",
        "view",
        "reward",
        "minutes",
        "agent_min",
        "tool_calls",
        "turns",
        "in_tok",
        "out_tok",
        "max_turn_tokens",
        "turns_8k",
        "wait_s",
        "chk",
    )
    prun = [
        {f: r[f] for f in keepf if f in r}
        | {"timeout": bool(r.get("timeout")), "replaces": r.get("replaces")}
        for r in allruns
    ]
    reader = None
    rd = os.path.join(DATA, "reader", subject)
    if os.path.isdir(rd):
        reader = {
            n: jload(os.path.join(rd, n + ".json"), default=None)
            for n in ("sbs", "mx", "notes", "walk", "cards", "rcards", "stories")
        }
    if reader:
        # written reader text is masked with the same grader values the leak scan checks (when grader files are present)
        sv, allstr = scrub.scan_values(scrub.alias_values(WORK))
        if sv:
            reader = {n: scrub.scrub_tree(v, sv, allstr) for n, v in reader.items()}
    gen = max((meta[k].get("generated") or "") for k in ks)
    return dict(
        subject=subject,
        models=ks,
        label={m: reg[m]["label"] for m in ks},
        color={m: reg[m]["color"] for m in ks},
        color_dark={m: reg[m].get("color_dark", reg[m]["color"]) for m in ks},
        V=V,
        matrix=matrix,
        runs=prun,
        tasks=tasks,
        keep=keep,
        drop=drop,
        pending_keys=pend,
        lsum=lsum,
        why=why,
        lt=lt,
        modes=modes,
        ltr=ltr,
        meta={m: {k: v for k, v in meta[m].items() if k not in ("api",)} for m in ks},
        reader=reader,
        generated=gen,
        prompts=jload(os.path.join(DATA, "prompts.json")),
        rerun_models=[m for m in ks if m in lsum],
    )
