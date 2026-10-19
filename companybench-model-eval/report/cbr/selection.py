"""Which runs a model's report is built from: the CSVs written by CB.exportCsv, read with the counting rule of the kit.

* the counted runs of a task are its first 3 exported rows (the export already holds only finished or timed-out runs,
  in launch order);
* the i-th run that timed out at 80 minutes is replaced, in the 5 hour view, by the i-th 5 hour rerun of that task;
* a timed-out run with no scored rerun is "pending": its task is dropped from the same-task 5 hour view for every model.
"""

import collections

from .common import read_csv, run_key

K = 3


def _int(v, d=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


def select(model_key, main_csv, long_csv=None):
    main = collections.defaultdict(list)
    for r in read_csv(main_csv):
        main[r["alias"]].append(r)
    longs = collections.defaultdict(list)
    for r in read_csv(long_csv) if long_csv else []:
        if r.get("run_id"):
            longs[r["alias"]].append(r)
    runs, rer, pending, problems = [], [], [], []
    for alias in sorted(main):
        rows = sorted(main[alias], key=lambda r: _int(r["slot"]))[:K]
        if len(rows) != K:
            problems.append(
                "%s has %d counted runs, expected %d" % (alias, len(rows), K)
            )
        lrows = sorted(longs.get(alias, []), key=lambda r: _int(r["slot"]))
        li = 0
        for r in rows:
            cell = _int(r["slot"])
            key = run_key(alias, model_key, cell)
            to = bool(_int(r["timed_out"]))
            ent = dict(
                key=key,
                alias=alias,
                cell=cell,
                view="80",
                run_id=_int(r["run_id"]),
                eval_id=_int(r["eval_id"]),
                task_id=_int(r["task_id"]),
                timeout=to,
                replaced_by=None,
            )
            if to:
                if li < len(lrows):
                    lr = lrows[li]
                    li += 1
                    ent["replaced_by"] = key + "L"
                    rer.append(
                        dict(
                            key=key + "L",
                            alias=alias,
                            cell=cell,
                            view="long",
                            replaces=key,
                            run_id=_int(lr["run_id"]),
                            eval_id=_int(lr["eval_id"]),
                            task_id=_int(lr["task_id"]),
                            timeout=bool(_int(lr["timed_out"])),
                        )
                    )
                else:
                    pending.append(key)
            runs.append(ent)
    return dict(
        model_key=model_key, runs=runs, long=rer, pending=pending, problems=problems
    )
