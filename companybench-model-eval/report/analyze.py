"""Step 2: turn the downloaded run records of one model into the files the site and the Doc are built from.

    python analyze.py --key Grok

Reads work/<key>/ (written by fetch.py). Writes work/models/<key>/ :
  runs.json        one row per counted run and per 5 hour rerun: score, minutes, tokens, cost, turns, largest turn, checks
  traces.json.gz   step timeline of every run (class, systems, minute, output tokens, seconds, masked command)
  full/<T>.json.gz masked step detail (reasoning, command, output) per task, for the trace player
  why.json         steps, errors, retries, polls, re-checks, unreadable replies, time in 8,000+ token turns
  longturns.json   long turns, re-check cycles, steps from first query to first deliverable
  longturn_runs.json  the long turns of each 80 minute run (turn number, tokens, seconds, what came next, topic)
  modes.json       rule-based failure mode of every run below full marks
  meta.json        counts for the method section (reruns scored and pending, provider stalls, turn-size counts)
To keep a finished model for the next report, copy that folder to data/models/<key>/ and commit it.
"""

import argparse
import collections
import datetime
import json
import os
import statistics as st

from cbr import modes as MODES
from cbr import runmetrics as RM
from cbr import scrub as SC
from cbr.common import FULL, WORK, jload, jsave, read_csv, reg_entry
from cbr.dataos import API


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--key", required=True)
    ap.add_argument(
        "--full",
        choices=["all", "misses", "none"],
        default="all",
        help="which runs get masked step detail",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="mask every number of 3+ digits and every decimal in step detail",
    )
    ap.add_argument("--out", help="output folder (default work/models/<key>)")
    a = ap.parse_args()
    key = a.key
    ent = reg_entry(key)
    base = os.path.join(WORK, key)
    out = a.out or os.path.join(WORK, "models", key)
    sel = jload(os.path.join(base, "selection.json"))
    entries = sel["runs"] + sel["long"]
    raw = lambda r: jload(os.path.join(base, "raw/runs/%d.json" % r["run_id"]))
    grd = lambda r: jload(
        os.path.join(base, "raw/graders/%d.json" % r["run_id"]), default={"content": ""}
    )

    # grader values per task: from this model's own graders of that task
    by_alias = collections.defaultdict(list)
    for r in entries:
        by_alias[r["alias"]].append(grd(r))
    masks = {al: SC.task_values(gs, limit=None) for al, gs in by_alias.items()}

    runs, traces, whyc, ltr, caps, modes, bundles = (
        [],
        {},
        {},
        {},
        collections.Counter(),
        {},
        collections.defaultdict(dict),
    )
    for i, r in enumerate(entries, 1):
        j = raw(r)
        m = RM.meta(j)
        seq = RM.trace(j)
        w = RM.why_counters(j)
        w["wait_requested_s"] = sum(s[7] for s in seq)
        lt = RM.longturn_run(j)
        cap = RM.cap_counts(j)
        caps.update(cap)
        m.update(
            key=r["key"],
            alias=r["alias"],
            model=key,
            cell=r["cell"],
            view=r["view"],
            timeout=r["timeout"],
            turns=len(seq),
            max_turn_tokens=max([s[4] for s in seq] or [0]),
            turns_8k=sum(1 for s in seq if s[4] >= RM.LONG),
            wait_s=w["wait_requested_s"],
        )
        if r["view"] == "long":
            m["replaces"] = r["replaces"]
        chk = RM.checks(grd(r))
        if chk:
            m["chk"] = chk
        runs.append(m)
        traces[r["key"]] = seq
        if r["view"] == "80":
            whyc[r["key"]] = (w, r["timeout"])
            ltr[r["key"]] = lt
            if m["reward"] < FULL:
                modes[r["key"]] = MODES.mode_of(m, w, lt, seq)
        elif m["reward"] < FULL:
            modes[r["key"]] = MODES.mode_of(dict(m, timeout=False), w, lt, seq)
        if a.full == "all" or (
            a.full == "misses" and (m["reward"] < FULL or r["view"] == "long")
        ):
            nums, strs = masks[r["alias"]]
            sc = lambda t: SC.scrub(t, nums, strs, a.strict)
            steps = RM.agent_steps(j)
            ent_steps, prev = [], None
            for n, s in enumerate(steps, 1):
                tt = RM.ts(s["timestamp"]) if s.get("timestamp") else None
                gap = round(tt - prev) if (tt and prev) else None
                prev = tt or prev
                calls = []
                for tc in s.get("tool_calls") or []:
                    ar = tc.get("arguments") or {}
                    arg = (
                        ar.get("keystrokes")
                        if "keystrokes" in ar
                        else json.dumps(ar)
                    )
                    calls.append([tc.get("function_name"), sc((arg or "")[:900])])
                ent_steps.append(
                    [
                        n,
                        gap,
                        (s.get("metrics") or {}).get("completion_tokens") or 0,
                        sc((s.get("message") or "")[:900]),
                        calls,
                        sc(RM.obs_text(s)[:1400]),
                    ]
                )
            bundles[r["alias"]][r["key"]] = ent_steps
        if i % 20 == 0:
            print("  analysed %d of %d runs" % (i, len(entries)), flush=True)

    ok80 = [k for k, (w, to) in whyc.items()]
    wrows = {}
    wrows[key] = RM.roll_why([whyc[k][0] for k in ok80])
    to_k = [k for k in ok80 if whyc[k][1]]
    fin_k = [k for k in ok80 if not whyc[k][1]]
    if to_k:
        wrows[key + "_timeout"] = RM.roll_why([whyc[k][0] for k in to_k])
    if fin_k:
        wrows[key + "_finished"] = RM.roll_why([whyc[k][0] for k in fin_k])
    ltroll = RM.roll_longturns([ltr[k] for k in ok80])

    # tokens per second of agent time, a plain speed measure that does not depend on how much the model writes
    tps = [
        x["out_tok"] / (x["agent_min"] * 60)
        for x in runs
        if x["view"] == "80" and x.get("agent_min") and x.get("out_tok")
    ]
    # provider stalls, from the evaluation lists
    att = []
    ap_ = os.path.join(base, "attempts.csv")
    if os.path.exists(ap_):
        mid = ent.get("dataos_id")
        for e in read_csv(ap_):
            if (
                (not mid or str(e["model_id"]) == str(mid))
                and str(e["agent"]) == "3"
                and e["status"] not in ("CANCELED", "CANCELLED")
            ):
                att.append(e)
    stall = lambda v: [e for e in att if e["view"] == v and "sent nothing" in e["exc"]]
    meta = dict(
        key=key,
        label=ent["label"],
        dataos_id=ent.get("dataos_id"),
        generated=datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        slots=sum(1 for r in sel["runs"] if r["timeout"]),
        scored=len(sel["long"]),
        pending=len(sel["pending"]),
        pending_keys=sel["pending"],
        attempts=(
            dict(
                evaluations=len(att),
                by_status=dict(collections.Counter(e["status"] for e in att)),
                stall80=len(stall("80")),
                stall_long=len(stall("long")),
                stall_long_tasks=len({e["alias"] for e in stall("long")}),
            )
            if att
            else None
        ),
        caps=dict(caps),
        tokens_per_second_median=round(st.median(tps), 1) if tps else None,
        api=API,
        runs=len(sel["runs"]),
    )
    jsave(os.path.join(out, "runs.json"), runs)
    jsave(os.path.join(out, "traces.json.gz"), traces)
    for al, b in bundles.items():
        jsave(os.path.join(out, "full", al + ".json.gz"), b)
    jsave(os.path.join(out, "longturn_runs.json"), {k: v["longs"] for k, v in ltr.items() if v["longs"]})
    jsave(os.path.join(out, "why.json"), wrows, indent=1)
    jsave(os.path.join(out, "longturns.json"), ltroll, indent=1)
    jsave(os.path.join(out, "modes.json"), modes, indent=1)
    jsave(os.path.join(out, "meta.json"), meta, indent=1)
    n80 = [x for x in runs if x["view"] == "80"]
    print(
        "%s: %d runs at 80 minutes, %d full marks, mean %.3f, %d timed out; %d reruns (%d pending)"
        % (
            key,
            len(n80),
            sum(1 for x in n80 if x["reward"] >= FULL),
            sum(x["reward"] for x in n80) / len(n80),
            sum(1 for x in n80 if x["timeout"]),
            meta["scored"],
            meta["pending"],
        )
    )
    print("saved to", out)


if __name__ == "__main__":
    main()
