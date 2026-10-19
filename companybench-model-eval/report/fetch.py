"""Step 1: download one model's run records, per-step traces and grader output from Data OS (read only).

    python fetch.py --key Grok --main companybench_model65_main.csv --long companybench_model65_long.csv

Reads the two CSVs that CB.exportCsv wrote (they hold the run ids). For every counted run and every 5 hour rerun it saves
the run record (with the full step trajectory) and the grader output. It also saves the evaluation list of each of the
40 tasks and of their 5 hour copies, which gives the provider-stall counts for the report.

Output (all under work/<key>/, gitignored): inputs/, selection.json, raw/runs/<run_id>.json, raw/graders/<run_id>.json,
attempts.csv. Safe to run again: files already downloaded are skipped.
"""

import argparse
import json
import os
import sys

from cbr import selection
from cbr.common import KIT, WORK, jload, jsave, read_csv, write_csv
from cbr.dataos import Client, TokenExpired


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--key",
        required=True,
        help="short model key used in run keys, e.g. Grok (letters and digits)",
    )
    ap.add_argument("--main", required=True, help="CSV from CB.exportCsv(id, 'main')")
    ap.add_argument(
        "--long",
        help="CSV from CB.exportCsv(id, 'long'); leave out when nothing timed out",
    )
    ap.add_argument("--token-file", default=os.path.join(WORK, "token.txt"))
    ap.add_argument(
        "--skip-attempts",
        action="store_true",
        help="do not read the evaluation lists (no stall counts)",
    )
    ap.add_argument(
        "--selection-only",
        action="store_true",
        help="write selection.json and stop; downloads nothing",
    )
    a = ap.parse_args()
    base = os.path.join(WORK, a.key)
    for sub in ("inputs", "raw/runs", "raw/graders"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    sel = selection.select(a.key, a.main, a.long)
    for p in sel["problems"]:
        print("WARNING:", p)
    if sel["problems"]:
        print(
            "Some tasks do not have 3 counted runs. Finish the 80 minute part first (CB.status), then export again."
        )
        sys.exit(2)
    jsave(os.path.join(base, "selection.json"), sel, indent=1)
    for src, name in ((a.main, "main.csv"), (a.long, "long.csv")):
        if src:
            with open(src, "rb") as i, open(
                os.path.join(base, "inputs", name), "wb"
            ) as o:
                o.write(i.read())
    print(
        "%s: %d counted runs, %d timed out at 80 minutes, %d reruns found, %d without a scored rerun"
        % (
            a.key,
            len(sel["runs"]),
            sum(r["timeout"] for r in sel["runs"]),
            len(sel["long"]),
            len(sel["pending"]),
        )
    )
    if a.selection_only:
        return
    cl = Client(a.token_file)
    todo = [r for r in sel["runs"] + sel["long"]]
    got = 0
    try:
        for i, r in enumerate(todo, 1):
            rp = os.path.join(base, "raw/runs/%d.json" % r["run_id"])
            gp = os.path.join(base, "raw/graders/%d.json" % r["run_id"])
            if not os.path.exists(rp):
                d = cl.run(r["run_id"])
                if not d or "trajectory" not in d:
                    print(
                        "WARNING: run %d (%s) has no trajectory in Data OS"
                        % (r["run_id"], r["key"])
                    )
                if d is not None:
                    jsave(rp, d)
                got += 1
            if not os.path.exists(gp):
                g = cl.grader(r["run_id"])
                jsave(gp, g if g is not None else {"content": ""})
            if i % 10 == 0 or i == len(todo):
                print("  %d of %d runs saved" % (i, len(todo)), flush=True)
        if not a.skip_attempts:
            tasks = jload(os.path.join(KIT, "tasks.json"))
            rows = []
            for t in tasks:
                for view, tid in (("80", t["task"]), ("long", t["long"])):
                    for e in cl.evaluations(tid):
                        m = e.get("model")
                        m = m.get("id") if isinstance(m, dict) else m
                        s = e.get("latest_run_summary") or {}
                        rows.append(
                            dict(
                                alias=t["alias"],
                                view=view,
                                eval_id=e["id"],
                                model_id=m,
                                agent=(
                                    (e.get("agent") or {}).get("id")
                                    if isinstance(e.get("agent"), dict)
                                    else e.get("agent")
                                ),
                                status=s.get("status"),
                                exc=(s.get("exception_info") or "")[:160].replace(
                                    "\n", " "
                                ),
                            )
                        )
                print("  evaluation lists read for", t["alias"], end="\r", flush=True)
            write_csv(
                os.path.join(base, "attempts.csv"),
                rows,
                ["alias", "view", "eval_id", "model_id", "agent", "status", "exc"],
            )
            print("\nevaluation lists saved:", len(rows), "rows")
    except TokenExpired as e:
        print(str(e))
        sys.exit(3)
    print("Done. Next: python analyze.py --key %s" % a.key)


if __name__ == "__main__":
    main()
