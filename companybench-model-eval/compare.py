"""Compare one new model against the four CompanyBench baseline models.

Usage:
    python compare.py --name "Grok 4.7" --main companybench_model65_main.csv [--long companybench_model65_long.csv]

Inputs are the CSV files written by CB.exportCsv(modelId, 'main') and CB.exportCsv(modelId, 'long').
The baseline (Gemini 4 Argon, Claude Fable 5.1, GPT 6.1 Sol, GPT 6 Astra) is baseline_perrun.csv.
Standard library only.

Rules (identical to the Gemini report):
  * a counted run is the first 3 finished runs per task, in the order they were launched;
  * "full marks" means a reward of 0.9999 or more;
  * the 5 hour view replaces each run that timed out at 80 minutes with the matching 5 hour rerun, in order;
  * tasks whose 5 hour rerun is not finished are dropped for ALL models in that view, so every model is scored
    on the same tasks. A second line scores those unfinished reruns as 0 over all 40 tasks.
"""

import argparse, collections, csv, os

HERE = os.path.dirname(os.path.abspath(__file__))
FULL = 0.9999


def load_baseline():
    rows = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in csv.DictReader(
        open(os.path.join(HERE, "baseline_perrun.csv"), encoding="utf-8")
    ):
        rows[r["model"]][r["alias"]].append(r)
    return rows


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def runs_of_new(path):
    by = collections.defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        by[r["alias"]].append(r)
    for a in by:
        by[a].sort(key=lambda r: int(r["slot"]))
    return by


def summarize(label, slots, tasks):
    """slots: {alias: [dict(reward, timeout, minutes, steps, cost)]}"""
    runs = [x for a in tasks for x in slots.get(a, [])]
    n = len(runs)
    if not n:
        return [label, "no runs", "", "", "", "", ""]
    full = sum(1 for x in runs if x["reward"] >= FULL)
    mean = sum(x["reward"] for x in runs) / n
    to = sum(1 for x in runs if x["timeout"])
    mins = [x["minutes"] for x in runs if x["minutes"] is not None]
    steps = [x["steps"] for x in runs if x["steps"] is not None]
    cost = [x["cost"] for x in runs if x["cost"] is not None]
    avg = lambda v: "%.1f" % (sum(v) / len(v)) if v else ""
    return [
        label,
        "%d of %d" % (full, n),
        "%.3f" % mean,
        "%d" % to,
        avg(mins),
        avg(steps),
        ("$%.2f" % (sum(cost) / len(cost))) if cost else "",
    ]


def as_slots_baseline(rows, view):
    out = {}
    for a, rs in rows.items():
        rs = sorted(rs, key=lambda r: int(num(r["slot"])))
        out[a] = [
            dict(
                reward=num(r["reward_swap" if view == "swap" else "reward80"]),
                timeout=int(num(r["timeout80"])) if view == "80" else 0,
                minutes=(
                    num(r["minutes_swap" if view == "swap" else "minutes80"], None)
                    if r["minutes80"] != ""
                    else None
                ),
                steps=(
                    num(r["steps_swap" if view == "swap" else "steps80"], None)
                    if r["steps80"] != ""
                    else None
                ),
                cost=(
                    num(r["cost_swap" if view == "swap" else "cost80"], None)
                    if r["cost80"] != ""
                    else None
                ),
            )
            for r in rs
        ]
    return out


def as_slots_new(main, long_):
    m80, swap, unfinished = {}, {}, set()
    for a, rs in main.items():
        m80[a] = [
            dict(
                reward=num(r["reward"]),
                timeout=int(num(r["timed_out"])),
                minutes=num(r["minutes"], None) if r["minutes"] != "" else None,
                steps=num(r["steps"], None) if r["steps"] != "" else None,
                cost=num(r["cost_usd"], None) if r["cost_usd"] != "" else None,
            )
            for r in rs
        ]
        reruns = list((long_ or {}).get(a, []))
        k = 0
        sw = []
        for x in m80[a]:
            if x["timeout"]:
                if k < len(reruns):
                    r = reruns[k]
                    k += 1
                    sw.append(
                        dict(
                            reward=num(r["reward"]),
                            timeout=0,
                            minutes=(
                                num(r["minutes"], None) if r["minutes"] != "" else None
                            ),
                            steps=num(r["steps"], None) if r["steps"] != "" else None,
                            cost=(
                                num(r["cost_usd"], None)
                                if r["cost_usd"] != ""
                                else None
                            ),
                        )
                    )
                else:
                    unfinished.add(a)
                    sw.append(
                        dict(
                            reward=0.0,
                            timeout=1,
                            minutes=x["minutes"],
                            steps=x["steps"],
                            cost=x["cost"],
                        )
                    )
            else:
                sw.append(x)
        swap[a] = sw
    return m80, swap, unfinished


def table(title, header, rows):
    print("\n" + title)
    w = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    print("  ".join(str(h).ljust(w[i]) for i, h in enumerate(header)))
    for r in rows:
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--main", required=True)
    ap.add_argument("--long")
    a = ap.parse_args()
    base = load_baseline()
    new_main = runs_of_new(a.main)
    new_long = runs_of_new(a.long) if a.long else None
    tasks = sorted({t for m in base.values() for t in m})
    problems = [t for t in tasks if len(new_main.get(t, [])) != 3]
    if problems:
        print(
            "WARNING: these tasks do not have exactly 3 counted runs yet: %s. Run CB.status first."
            % ", ".join(problems)
        )
    hdr = [
        "Model",
        "Full marks",
        "Mean score",
        "Timed out",
        "Minutes/run",
        "Steps/run",
        "Cost/run",
    ]
    names = {
        "Argon": "Gemini 4 Argon",
        "Fable": "Claude Fable 5.1",
        "Sol": "GPT 6.1 Sol",
        "Astra": "GPT 6 Astra",
    }
    rows80 = [
        summarize(names.get(m, m), as_slots_baseline(base[m], "80"), tasks)
        for m in ("Argon", "Fable", "Sol", "Astra")
    ]
    n80, nsw, unfinished = as_slots_new(new_main, new_long)
    rows80.append(summarize(a.name, n80, tasks))
    table("80 MINUTE VIEW, all %d tasks, 3 runs each" % len(tasks), hdr, rows80)
    if a.long:
        keep = [t for t in tasks if t not in unfinished]
        rowsw = [
            summarize(names.get(m, m), as_slots_baseline(base[m], "swap"), keep)
            for m in ("Argon", "Fable", "Sol", "Astra")
        ]
        rowsw.append(summarize(a.name, nsw, keep))
        table(
            "5 HOUR VIEW, same %d tasks for every model (tasks with an unfinished rerun dropped for all models)"
            % len(keep),
            hdr,
            rowsw,
        )
        rowsz = [
            summarize(names.get(m, m), as_slots_baseline(base[m], "swap"), tasks)
            for m in ("Argon", "Fable", "Sol", "Astra")
        ]
        rowsz.append(summarize(a.name, nsw, tasks))
        table(
            "5 HOUR VIEW, all %d tasks, reruns that did not finish scored as 0"
            % len(tasks),
            hdr,
            rowsz,
        )
        print(
            "\nTasks dropped from the same-task view: %s"
            % (", ".join(sorted(unfinished)) or "none")
        )
    print(
        "\nBaseline model scores for the 5 hour view of Argon use its own reruns; Claude and GPT never timed out, so their 5 hour scores equal their 80 minute scores."
    )


if __name__ == "__main__":
    main()
